"""Queries de análise: dead code detection e hotspots.

Dead code: símbolos definidos (function/method/class) que não têm nenhum
caller/import/inherits incoming. Pontos de entrada (entrypoints) podem ser
excluídos da análise via parâmetro.

Hotspots: símbolos mais referenciados (in-degree alto no grafo de chamadas
e imports), indicando pontos críticos de acoplamento.
"""

from __future__ import annotations

from typing import Any

from eizo.graph.models import Node
from eizo.graph.store import GraphStore

# Kinds que representam definições de símbolos — candidatos a dead code.
_DEFINITION_KINDS: frozenset[str] = frozenset({"function", "method", "class"})

# Nomes que são tipicamente entrypoints e não devem ser marcados como dead code
# mesmo sem callers explícitos no grafo.
_DEFAULT_ENTRYPOINTS: frozenset[str] = frozenset({
    "main", "__main__", "run", "serve", "app", "create_app",
    "setup", "teardown", "handle", "cli",
})


def find_dead_code(
    store: GraphStore,
    entrypoints: frozenset[str] | None = None,
    limit: int = 100,
) -> list[Node]:
    """Encontra símbolos definidos sem nenhum dependente (dead code).

    Um símbolo é considerado "dead" se:
    - É uma definição (function, method, class)
    - Não tem arestas incoming (calls, imports, inherits)
    - Seu nome não está na lista de entrypoints conhecidos

    Args:
        store: GraphStore com o grafo.
        entrypoints: Nomes de entrypoints a excluir da análise. Se None,
            usa _DEFAULT_ENTRYPOINTS.
        limit: Máximo de resultados.

    Returns:
        Lista de Nodes considerados dead code, ordenados por arquivo + linha.
    """
    if entrypoints is None:
        entrypoints = _DEFAULT_ENTRYPOINTS

    # Busca todas as definições que não têm nenhuma aresta incoming.
    # Uma aresta incoming significa que alguém chama, importa ou herda este símbolo.
    sql = """
        SELECT n.* FROM nodes n
        WHERE n.kind IN ('function', 'method', 'class')
          AND n.id NOT IN (SELECT DISTINCT target_id FROM edges)
          AND n.name NOT IN ({placeholders})
        ORDER BY n.file_path, n.line_start
        LIMIT ?
    """

    # Constrói placeholders dinamicamente para a lista de entrypoints
    eps = list(entrypoints)
    if eps:
        placeholders = ",".join("?" * len(eps))
        sql = sql.format(placeholders=placeholders)
        params: list[Any] = eps + [limit]
    else:
        # Sem entrypoints — query sem filtro de nome
        sql = """
            SELECT n.* FROM nodes n
            WHERE n.kind IN ('function', 'method', 'class')
              AND n.id NOT IN (SELECT DISTINCT target_id FROM edges)
            ORDER BY n.file_path, n.line_start
            LIMIT ?
        """
        params = [limit]

    rows = store.conn.execute(sql, params).fetchall()
    # Filtra nós stub externos (metadata.external = True) — não são dead code,
    # são referências a símbolos de fora do repo.
    nodes = [store._row_to_node(r) for r in rows]
    return [n for n in nodes if not n.metadata.get("external")]


def find_hotspots(
    store: GraphStore,
    limit: int = 20,
    min_references: int = 2,
) -> list[dict[str, Any]]:
    """Encontra símbolos mais referenciados (hotspots).

    Conta o in-degree (número de arestas incoming) para cada nó de definição.
    Símbolos com muitas referências são pontos críticos — mudanças neles
    têm alto impacto.

    Args:
        store: GraphStore com o grafo.
        limit: Máximo de resultados.
        min_references: Mínimo de referências para aparecer no resultado.

    Returns:
        Lista de dicts com 'node' (Node) e 'reference_count' (int),
        ordenada por reference_count descendente.
    """
    sql = """
        SELECT n.*, COUNT(e.source_id) as ref_count
        FROM nodes n
        JOIN edges e ON e.target_id = n.id
        WHERE n.kind IN ('function', 'method', 'class')
        GROUP BY n.id
        HAVING ref_count >= ?
        ORDER BY ref_count DESC, n.name
        LIMIT ?
    """

    rows = store.conn.execute(sql, [min_references, limit]).fetchall()
    results: list[dict[str, Any]] = []
    for r in rows:
        node = store._row_to_node(r)
        ref_count = r["ref_count"]
        results.append({"node": node, "reference_count": ref_count})

    return results
