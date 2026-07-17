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


def _real_referrers(store: GraphStore, node: Node) -> list[Node]:
    """Encontra quem realmente referencia esta definição (calls/imports/inherits).

    O parser cria arestas `contains` (arquivo/classe → membro) que não indicam
    uso — apenas estrutura. Ele também cria arestas `caller → call_site` em vez
    de `caller → definição` para chamadas. Por isso, referências reais precisam
    resolver ambos os caminhos, igual a `trace.py`/`impact.py`:

    - Caminho 1: arestas `calls`/`imports`/`inherits` diretas para esta definição.
    - Caminho 2: nós `kind='call'` com o mesmo nome, subindo via `calls` até
      quem fez a chamada.

    Retorna a lista (deduplicada por id) de nós que referenciam `node`.
    """
    referrers: dict[str, Node] = {}

    for kind in ("calls", "imports", "inherits"):
        for edge in store.get_incoming_edges(node.id, kind=kind):
            referrer = store.get_node(edge.source_id)
            if referrer:
                referrers[referrer.id] = referrer

    call_sites = store.get_nodes_by_name(node.name, kind="call")
    for call_site in call_sites:
        if call_site.id == node.id:
            continue
        for edge in store.get_incoming_edges(call_site.id, kind="calls"):
            referrer = store.get_node(edge.source_id)
            if referrer:
                referrers[referrer.id] = referrer

    return list(referrers.values())


def _definition_nodes(store: GraphStore) -> list[Node]:
    """Retorna todos os nós de definição (function/method/class), sem stubs externos."""
    rows = store.conn.execute(
        "SELECT * FROM nodes WHERE kind IN ('function', 'method', 'class') "
        "ORDER BY file_path, line_start"
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
