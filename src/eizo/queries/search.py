"""Queries de busca no grafo de conhecimento."""

from __future__ import annotations

from typing import Any

from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore


def search_symbols(
    store: GraphStore,
    query: str,
    kind: str | None = None,
    language: str | None = None,
    limit: int = 50,
) -> list[Node]:
    """Busca símbolos por nome."""
    return store.search_nodes(query, kind=kind, language=language, limit=limit)


def get_symbol_context(
    store: GraphStore,
    node_id: str,
    depth: int = 1,
) -> dict[str, Any]:
    """Retorna o contexto completo de um símbolo: ele mesmo + vizinhança.

    Args:
        store: GraphStore.
        node_id: ID do nó.
        depth: Profundidade da vizinhança (1 = diretos, 2 = até netos).

    Returns:
        Dict com 'node', 'incoming', 'outgoing', 'file_nodes'.
    """
    node = store.get_node(node_id)
    if node is None:
        return {"node": None, "incoming": [], "outgoing": [], "file_nodes": []}

    incoming = store.get_incoming_edges(node_id)
    outgoing = store.get_outgoing_edges(node_id)

    # Nós do mesmo arquivo
    file_nodes = store.get_nodes_by_file(node.file_path)

    result: dict[str, Any] = {
        "node": node,
        "incoming": incoming,
        "outgoing": outgoing,
        "file_nodes": file_nodes,
    }

    if depth > 1:
        # Expande vizinhança
        deeper_incoming: list[Edge] = []
        deeper_outgoing: list[Edge] = []
        seen: set[str] = {node_id}

        for edge in incoming:
            if edge.source_id not in seen:
                seen.add(edge.source_id)
                deeper_incoming.extend(store.get_incoming_edges(edge.source_id))
                deeper_outgoing.extend(store.get_outgoing_edges(edge.source_id))
        for edge in outgoing:
            if edge.target_id not in seen:
                seen.add(edge.target_id)
                deeper_incoming.extend(store.get_incoming_edges(edge.target_id))
                deeper_outgoing.extend(store.get_outgoing_edges(edge.target_id))

        result["deeper_incoming"] = deeper_incoming
        result["deeper_outgoing"] = deeper_outgoing

    return result
