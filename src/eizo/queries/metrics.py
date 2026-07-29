"""Métricas por símbolo: fan-in, fan-out e LOC.

Usa dados já existentes no grafo — arestas resolvidas (`real_referrers` /
`resolve_call_to_definition`) e `line_start`/`line_end` dos nós — sem exigir
nenhuma análise nova de AST. Complexidade ciclomática fica fora de escopo:
exigiria tocar os dois parsers para contar branches, mais superfície de
risco por um ganho que este comando não promete entregar.
"""

from __future__ import annotations

from typing import Any

from eizo.graph.models import DEFINITION_KINDS, Node
from eizo.graph.store import GraphStore
from eizo.queries.analysis import real_referrers


def _fan_out(store: GraphStore, node: Node) -> int:
    """Quantos alvos distintos este símbolo referencia.

    Considera arestas `calls` e `inherits` — ambas já têm resolução de
    call-site/stub para a definição real via `resolve_call_to_definition`
    (mesmo mecanismo usado por `trace_call_path` no sentido outgoing).
    `imports` fica fora: resolver um import para o arquivo real alvo é uma
    heurística à parte (ver `queries.cycles`), conceitualmente distinta de
    "o que este símbolo usa".
    """
    targets: dict[str, Node] = {}
    for kind in ("calls", "inherits"):
        for edge in store.get_outgoing_edges(node.id, kind=kind):
            target = store.get_node(edge.target_id)
            if target is None:
                continue
            resolved = store.resolve_call_to_definition(target)
            targets[resolved.id] = resolved
    return len(targets)


def _loc(node: Node) -> int | None:
    """Linhas de código do símbolo, ou None se a extensão não foi capturada."""
    if node.line_start is None or node.line_end is None:
        return None
    return node.line_end - node.line_start + 1


def compute_symbol_metrics(store: GraphStore, symbol_name: str) -> list[dict[str, Any]]:
    """Calcula fan-in, fan-out e LOC para cada definição homônima a `symbol_name`.

    Pode haver mais de uma definição com o mesmo nome em arquivos diferentes
    — todas são retornadas, uma entrada por definição.

    Args:
        store: GraphStore.
        symbol_name: Nome exato do símbolo (function/method/class).

    Returns:
        Lista de dicts com 'node', 'fan_in', 'fan_out', 'loc' — uma entrada
        por definição homônima encontrada.
    """
    # Exclui stubs externos (metadata.external=True) — criados pela resolução
    # de herança/call quando o alvo real não existe ou ainda não foi
    # encontrado no grafo (ver graph/store.py). Um stub tem kind='class' ou
    # 'function' igual a uma definição real, mas não é uma.
    candidates = [
        n
        for n in store.get_nodes_by_name(symbol_name)
        if n.kind in DEFINITION_KINDS and not n.metadata.get("external")
    ]

    results: list[dict[str, Any]] = []
    for node in candidates:
        results.append({
            "node": node,
            "fan_in": len(real_referrers(store, node)),
            "fan_out": _fan_out(store, node),
            "loc": _loc(node),
        })
    return results
