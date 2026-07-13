"""Queries de trace (call graph) no grafo de conhecimento."""

from __future__ import annotations

from typing import Any

from eizo.graph.store import GraphStore


def trace_call_path(
    store: GraphStore,
    symbol_name: str,
    direction: str = "both",
    max_depth: int = 5,
) -> dict[str, Any]:
    """Traça o caminho de chamadas de/para um símbolo.

    Args:
        store: GraphStore.
        symbol_name: Nome do símbolo a traçar.
        direction: 'incoming' (quem chama), 'outgoing' (quem é chamado), 'both'.
        max_depth: Profundidade máxima da busca.

    Returns:
        Dict com 'symbol', 'callers' (incoming), 'callees' (outgoing).
    """
    # Encontra o nó pelo nome
    nodes = store.search_nodes(symbol_name, limit=10)
    if not nodes:
        return {"symbol": None, "callers": [], "callees": []}

    symbol = nodes[0]

    callers: list[dict[str, Any]] = []
    callees: list[dict[str, Any]] = []

    if direction in ("incoming", "both"):
        callers = _trace_incoming(store, symbol.id, max_depth)

    if direction in ("outgoing", "both"):
        callees = _trace_outgoing(store, symbol.id, max_depth)

    return {
        "symbol": symbol,
        "callers": callers,
        "callees": callees,
    }


def _trace_incoming(
    store: GraphStore,
    node_id: str,
    max_depth: int,
    current_depth: int = 0,
    visited: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Traça chamadas que chegam a um nó (quem chama este símbolo)."""
    if visited is None:
        visited = set()

    if current_depth >= max_depth or node_id in visited:
        return []

    visited.add(node_id)
    results: list[dict[str, Any]] = []

    edges = store.get_incoming_edges(node_id, kind="calls")
    for edge in edges:
        caller = store.get_node(edge.source_id)
        if caller:
            entry: dict[str, Any] = {
                "node": caller,
                "depth": current_depth + 1,
            }
            deeper = _trace_incoming(store, caller.id, max_depth, current_depth + 1, visited)
            if deeper:
                entry["callers"] = deeper
            results.append(entry)

    return results


def _trace_outgoing(
    store: GraphStore,
    node_id: str,
    max_depth: int,
    current_depth: int = 0,
    visited: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Traça chamadas que saem de um nó (quem este símbolo chama)."""
    if visited is None:
        visited = set()

    if current_depth >= max_depth or node_id in visited:
        return []

    visited.add(node_id)
    results: list[dict[str, Any]] = []

    edges = store.get_outgoing_edges(node_id, kind="calls")
    for edge in edges:
        callee = store.get_node(edge.target_id)
        if callee:
            entry: dict[str, Any] = {
                "node": callee,
                "depth": current_depth + 1,
            }
            deeper = _trace_outgoing(store, callee.id, max_depth, current_depth + 1, visited)
            if deeper:
                entry["callees"] = deeper
            results.append(entry)

    return results
