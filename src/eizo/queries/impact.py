"""Queries de análise de impacto no grafo de conhecimento."""

from __future__ import annotations

from typing import Any

from eizo.graph.models import Node
from eizo.graph.store import GraphStore

# Kinds que representam definições de símbolos (não call sites).
_DEFINITION_KINDS: frozenset[str] = frozenset({"function", "method", "class"})


def _resolve_symbol(nodes: list[Node]) -> Node:
    """Seleciona definição com match exato primeiro; fallback para primeiro nó."""
    for n in nodes:
        if n.kind in _DEFINITION_KINDS:
            return n
    return nodes[0]


def analyze_impact(
    store: GraphStore,
    symbol_name: str,
    max_depth: int = 3,
) -> dict[str, Any]:
    """Analisa o impacto de mudança em um símbolo.

    Mapeia a cadeia de dependências: quem depende deste símbolo
    (diretos e transitivos).

    Args:
        store: GraphStore.
        symbol_name: Nome do símbolo a analisar.
        max_depth: Profundidade máxima da cadeia.

    Returns:
        Dict com 'symbol', 'impact_chain' (árvore de dependentes).
    """
    nodes = store.search_nodes(symbol_name, limit=10)
    if not nodes:
        return {"symbol": None, "impact_chain": []}

    symbol = _resolve_symbol(nodes)
    impact_chain = _build_impact_chain(store, symbol.id, max_depth)

    return {
        "symbol": symbol,
        "impact_chain": impact_chain,
    }


def _build_impact_chain(
    store: GraphStore,
    node_id: str,
    max_depth: int,
    current_depth: int = 0,
    visited: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Constrói a cadeia de impacto recursivamente."""
    if visited is None:
        visited = set()

    if current_depth >= max_depth or node_id in visited:
        return []

    visited.add(node_id)
    results: list[dict[str, Any]] = []
    seen_callers: set[str] = set()

    # Quem importa este símbolo
    import_edges = store.get_incoming_edges(node_id, kind="imports")
    for edge in import_edges:
        dependent = store.get_node(edge.source_id)
        if dependent:
            imp_entry: dict[str, Any] = {
                "node": dependent,
                "relation": "imports",
                "depth": current_depth + 1,
            }
            deeper = _build_impact_chain(store, dependent.id, max_depth, current_depth + 1, visited)
            if deeper:
                imp_entry["dependents"] = deeper
            results.append(imp_entry)

    # Quem herda deste símbolo
    inherit_edges = store.get_incoming_edges(node_id, kind="inherits")
    for edge in inherit_edges:
        dependent = store.get_node(edge.source_id)
        if dependent:
            inh_entry: dict[str, Any] = {
                "node": dependent,
                "relation": "inherits",
                "depth": current_depth + 1,
            }
            deeper = _build_impact_chain(store, dependent.id, max_depth, current_depth + 1, visited)
            if deeper:
                inh_entry["dependents"] = deeper
            results.append(inh_entry)

    # Quem chama este símbolo (arestas diretas)
    call_edges = store.get_incoming_edges(node_id, kind="calls")
    for edge in call_edges:
        dependent = store.get_node(edge.source_id)
        if dependent:
            if dependent.id in seen_callers:
                continue
            seen_callers.add(dependent.id)
            call_entry: dict[str, Any] = {
                "node": dependent,
                "relation": "calls",
                "depth": current_depth + 1,
            }
            deeper = _build_impact_chain(store, dependent.id, max_depth, current_depth + 1, visited)
            if deeper:
                call_entry["dependents"] = deeper
            results.append(call_entry)

    # Quem chama este símbolo via call sites (caller → call_site com mesmo nome)
    target = store.get_node(node_id)
    if target is not None:
        call_sites = store.get_nodes_by_name(target.name, kind="call")
        for call_site in call_sites:
            if call_site.id == node_id:
                continue
            site_edges = store.get_incoming_edges(call_site.id, kind="calls")
            for edge in site_edges:
                dependent = store.get_node(edge.source_id)
                if not dependent:
                    continue
                if dependent.id in seen_callers:
                    continue
                seen_callers.add(dependent.id)
                call_entry2: dict[str, Any] = {
                    "node": dependent,
                    "relation": "calls",
                    "depth": current_depth + 1,
                }
                deeper2 = _build_impact_chain(
                    store, dependent.id, max_depth, current_depth + 1, visited
                )
                if deeper2:
                    call_entry2["dependents"] = deeper2
                results.append(call_entry2)

    return results
