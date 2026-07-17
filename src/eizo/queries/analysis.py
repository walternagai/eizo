"""Queries de análise: dead code detection e hotspots.

Dead code: símbolos definidos (function/method/class) que não têm nenhum
caller/import/inherits incoming. Pontos de entrada (entrypoints) podem ser
excluídos da análise via parâmetro.

Hotspots: símbolos mais referenciados (in-degree alto no grafo de chamadas
e imports), indicando pontos críticos de acoplamento.
"""

from __future__ import annotations

from typing import Any

from eizo.graph.models import DEFINITION_KINDS, Node
from eizo.graph.store import GraphStore

# Nomes que são tipicamente entrypoints e não devem ser marcados como dead code
# mesmo sem callers explícitos no grafo.
_DEFAULT_ENTRYPOINTS: frozenset[str] = frozenset({
    "main", "__main__", "run", "serve", "app", "create_app",
    "setup", "teardown", "handle", "cli",
})


def _real_referrers(store: GraphStore, node: Node) -> list[Node]:
    """Encontra quem realmente referencia esta definição (calls/imports/inherits).

    Delega a `store.get_real_references`, que resolve o padrão
    caller → call_site → definição usado pelo parser (ver `trace.py`/
    `impact.py`, que resolvem o mesmo padrão para os respectivos casos de uso).

    Deduplica por id (não por (id, kind)): um caller que tanto importa quanto
    chama `node` deve contar como uma única referência para dead code/hotspots.
    """
    seen: dict[str, Node] = {}
    for referrer, _kind in store.get_real_references(node.id, node.name):
        seen[referrer.id] = referrer
    return list(seen.values())


def _definition_nodes(store: GraphStore) -> list[Node]:
    """Retorna todos os nós de definição (function/method/class), sem stubs externos."""
    placeholders = ",".join("?" for _ in DEFINITION_KINDS)
    rows = store.conn.execute(
        f"SELECT * FROM nodes WHERE kind IN ({placeholders}) "
        "ORDER BY file_path, line_start",
        tuple(DEFINITION_KINDS),
    ).fetchall()
    nodes = [store._row_to_node(r) for r in rows]
    return [n for n in nodes if not n.metadata.get("external")]


def find_dead_code(
    store: GraphStore,
    entrypoints: frozenset[str] | None = None,
    limit: int = 100,
) -> list[Node]:
    """Encontra símbolos definidos sem nenhum dependente (dead code).

    Um símbolo é considerado "dead" se:
    - É uma definição (function, method, class)
    - Ninguém realmente o chama, importa ou herda dele (ver `_real_referrers`)
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

    dead: list[Node] = []
    for node in _definition_nodes(store):
        if node.name in entrypoints:
            continue
        if _real_referrers(store, node):
            continue
        dead.append(node)
        if len(dead) >= limit:
            break

    return dead


def find_hotspots(
    store: GraphStore,
    limit: int = 20,
    min_references: int = 2,
) -> list[dict[str, Any]]:
    """Encontra símbolos mais referenciados (hotspots).

    Conta referências reais (calls/imports/inherits, resolvendo call sites —
    ver `_real_referrers`) para cada nó de definição. Símbolos com muitas
    referências são pontos críticos — mudanças neles têm alto impacto.

    Args:
        store: GraphStore com o grafo.
        limit: Máximo de resultados.
        min_references: Mínimo de referências para aparecer no resultado.

    Returns:
        Lista de dicts com 'node' (Node) e 'reference_count' (int),
        ordenada por reference_count descendente.
    """
    results: list[dict[str, Any]] = []
    for node in _definition_nodes(store):
        ref_count = len(_real_referrers(store, node))
        if ref_count >= min_references:
            results.append({"node": node, "reference_count": ref_count})

    results.sort(key=lambda r: (-r["reference_count"], r["node"].name))
    return results[:limit]
