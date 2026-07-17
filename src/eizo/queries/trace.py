"""Queries de trace (call graph) no grafo de conhecimento."""

from __future__ import annotations

from typing import Any

from eizo.graph.models import DEFINITION_KINDS, Node
from eizo.graph.store import GraphStore


def _resolve_symbol(nodes: list[Node]) -> Node:
    """Seleciona o melhor nó para um trace: definição com match exato primeiro.

    O parser cria nós kind='call' (call sites) além das definições. Para um
    trace com sentido semântico, priorizamos definições (function/method/class)
    com match exato de nome. Se não houver, caímos para o primeiro nó.
    """
    # search_nodes já ordena definições antes de call sites, mas garantimos
    # aqui para robustez (caso chamem com lista vinda de outro caminho).
    for n in nodes:
        if n.kind in DEFINITION_KINDS:
            return n
    # Fallback: primeiro nó (call site, import, file).
    return nodes[0]


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

    symbol = _resolve_symbol(nodes)

    callers: list[dict[str, Any]] = []
    callees: list[dict[str, Any]] = []

    if direction in ("incoming", "both"):
        callers = _trace_incoming(store, symbol.id, symbol.name, max_depth)

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
    node_name: str,
    max_depth: int,
    current_depth: int = 0,
    ancestors: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Traça chamadas que chegam a um nó (quem chama este símbolo).

    Usa `store.get_real_references`, que resolve tanto arestas `calls`
    diretas (caller → este_nó) quanto nós `kind='call'` com mesmo nome
    (call sites) subindo via `calls` até quem fez a chamada — cobre o caso
    em que o parser criou caller → call_site em vez de caller → definição.

    Usa `ancestors` per-branch: cada ramo mantém o próprio conjunto de nós
    no caminho da raiz até ele. Assim, todos os caminhos válidos aparecem
    (não há poda indevida entre ramos irmãos), mas ciclos ainda são evitados
    (um nó não aparece como descendente de si mesmo).
    """
    if ancestors is None:
        ancestors = set()

    if current_depth >= max_depth:
        return []

    results: list[dict[str, Any]] = []

    for caller, kind in store.get_real_references(node_id, node_name):
        if kind != "calls":
            continue

        if caller.id in ancestors:
            results.append({
                "node": caller,
                "depth": current_depth + 1,
                "cycle": True,
            })
            continue

        entry: dict[str, Any] = {
            "node": caller,
            "depth": current_depth + 1,
        }
        deeper = _trace_incoming(
            store, caller.id, caller.name, max_depth, current_depth + 1, ancestors | {node_id}
        )
        if deeper:
            entry["callers"] = deeper
        results.append(entry)

    return results


def _trace_outgoing(
    store: GraphStore,
    node_id: str,
    max_depth: int,
    current_depth: int = 0,
    ancestors: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Traça chamadas que saem de um nó (quem este símbolo chama).

    Quando o parser cria arestas caller → call_site, o trace outgoing
    precisa resolver o call site para a definição alvo. Se não houver
    definição correspondente, mantém o call site (preserva informação).

    Usa `ancestors` per-branch — ver `_trace_incoming` para justificativa.
    """
    if ancestors is None:
        ancestors = set()

    if current_depth >= max_depth:
        return []

    results: list[dict[str, Any]] = []
    seen_targets: set[str] = set()

    edges = store.get_outgoing_edges(node_id, kind="calls")
    for edge in edges:
        target = store.get_node(edge.target_id)
        if not target:
            continue

        # Se target é call site, resolve para a definição real.
        if target.kind == "call":
            resolved = store.resolve_call_to_definition(target)
            if resolved.id != target.id:
                target = resolved

        if target.id in seen_targets:
            continue
        seen_targets.add(target.id)

        if target.id in ancestors:
            results.append({
                "node": target,
                "depth": current_depth + 1,
                "cycle": True,
            })
            continue

        entry: dict[str, Any] = {
            "node": target,
            "depth": current_depth + 1,
        }
        deeper = _trace_outgoing(
            store, target.id, max_depth, current_depth + 1, ancestors | {node_id}
        )
        if deeper:
            entry["callees"] = deeper
        results.append(entry)

    return results
