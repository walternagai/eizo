"""Queries de trace (call graph) no grafo de conhecimento."""

from __future__ import annotations

from typing import Any

from eizo.graph.models import Node
from eizo.graph.store import GraphStore

# Kinds que representam definições de símbolos (não call sites).
_DEFINITION_KINDS: frozenset[str] = frozenset({"function", "method", "class"})


def _resolve_symbol(nodes: list[Node]) -> Node:
    """Seleciona o melhor nó para um trace: definição com match exato primeiro.

    O parser cria nós kind='call' (call sites) além das definições. Para um
    trace com sentido semântico, priorizamos definições (function/method/class)
    com match exato de nome. Se não houver, caímos para o primeiro nó.
    """
    # search_nodes já ordena definições antes de call sites, mas garantimos
    # aqui para robustez (caso chamem com lista vinda de outro caminho).
    for n in nodes:
        if n.kind in _DEFINITION_KINDS:
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


def _resolve_call_to_definition(store: GraphStore, call_node: Node) -> Node | None:
    """Dado um nó kind='call', tenta achar a definição com mesmo nome.

    O parser cria arestas caller → call_site (não caller → definição). Para
    que o trace outgoing mostre quem é realmente chamado, resolvemos o call
    site para uma definição (function/method/class) com mesmo nome.
    """
    candidates = store.get_nodes_by_name(call_node.name)
    # Prefer definição; se não houver, retorna o próprio call_node (preserva info).
    for n in candidates:
        if n.kind in _DEFINITION_KINDS:
            return n
    return call_node


def _trace_incoming(
    store: GraphStore,
    node_id: str,
    node_name: str,
    max_depth: int,
    current_depth: int = 0,
    ancestors: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Traça chamadas que chegam a um nó (quem chama este símbolo).

    Além das arestas `calls` diretas (caller → este_nó), também procura
    nós `kind='call'` com mesmo nome (call sites) e sobe via aresta
    `calls` do caller do call site. Isso cobre o caso em que o parser
    criou caller → call_site em vez de caller → definição.

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
    seen_callers: set[str] = set()

    # Caminho 1: arestas calls diretas para este nó (modelo antigo / testes).
    edges = store.get_incoming_edges(node_id, kind="calls")
    for edge in edges:
        caller = store.get_node(edge.source_id)
        if not caller:
            continue

        if caller.id in seen_callers:
            continue
        seen_callers.add(caller.id)

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

    # Caminho 2: call sites com mesmo nome → sobe para o caller do call site.
    call_sites = store.get_nodes_by_name(node_name, kind="call")
    for call_site in call_sites:
        if call_site.id == node_id:
            continue
        site_edges = store.get_incoming_edges(call_site.id, kind="calls")
        for edge in site_edges:
            caller = store.get_node(edge.source_id)
            if not caller:
                continue

            if caller.id in seen_callers:
                continue
            seen_callers.add(caller.id)

            if caller.id in ancestors:
                results.append({
                    "node": caller,
                    "depth": current_depth + 1,
                    "cycle": True,
                })
                continue

            entry2: dict[str, Any] = {
                "node": caller,
                "depth": current_depth + 1,
            }
            deeper2 = _trace_incoming(
                store, caller.id, caller.name, max_depth, current_depth + 1, ancestors | {node_id}
            )
            if deeper2:
                entry2["callers"] = deeper2
            results.append(entry2)

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

        # Fix B: se target é call site, resolve para definição.
        if target.kind == "call":
            resolved = _resolve_call_to_definition(store, target)
            if resolved is not None and resolved.id != target.id:
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
