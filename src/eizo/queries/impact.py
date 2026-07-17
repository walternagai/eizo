"""Queries de análise de impacto no grafo de conhecimento."""

from __future__ import annotations

from typing import Any

from eizo.graph.models import DEFINITION_KINDS, Node
from eizo.graph.store import GraphStore


def _resolve_symbol(nodes: list[Node]) -> Node:
    """Seleciona definição com match exato primeiro; fallback para primeiro nó."""
    for n in nodes:
        if n.kind in DEFINITION_KINDS:
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
    """Constrói a cadeia de impacto recursivamente.

    Usa `store.get_real_references`, que resolve dependentes via
    imports/inherits/calls diretos e via call sites (caller → call_site
    com mesmo nome — padrão usado pelo parser para chamadas).
    """
    if visited is None:
        visited = set()

    if current_depth >= max_depth or node_id in visited:
        return []

    visited.add(node_id)

    node = store.get_node(node_id)
    if node is None:
        return []

    results: list[dict[str, Any]] = []
    for dependent, relation in store.get_real_references(node_id, node.name):
        entry: dict[str, Any] = {
            "node": dependent,
            "relation": relation,
            "depth": current_depth + 1,
        }
        deeper = _build_impact_chain(store, dependent.id, max_depth, current_depth + 1, visited)
        if deeper:
            entry["dependents"] = deeper
        results.append(entry)

    return results
