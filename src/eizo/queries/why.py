"""`why` — explica por que dois símbolos estão acoplados.

Faz o inverso de `trace`: em vez de "o que este símbolo chama", responde
"por que A e B estão conectados", achando o caminho mais curto de A até B
(ou de B até A, se só existir na direção contrária) seguindo arestas
`calls`/`inherits` resolvidas — mesma resolução de call-site/stub usada por
`trace_call_path` e `metrics._fan_out`.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from eizo.graph.models import DEFINITION_KINDS, Node
from eizo.graph.store import GraphStore

_EDGE_KINDS = ("calls", "inherits")


def _resolve_symbol(store: GraphStore, name: str) -> Node | None:
    """Resolve um nome para o melhor nó — definição com match exato primeiro.

    Mesma heurística usada por `trace.py` e `impact.py`: prioriza
    function/method/class sobre call sites/imports/arquivos.
    """
    nodes = store.search_nodes(name, limit=10)
    if not nodes:
        return None
    for n in nodes:
        if n.kind in DEFINITION_KINDS:
            return n
    return nodes[0]


def _bfs_path(store: GraphStore, start: Node, target_name: str, max_depth: int) -> list[Node] | None:
    """BFS a partir de `start` via calls/inherits, procurando um nó com nome
    `target_name`. BFS garante o caminho mais curto (menor número de saltos).

    Retorna a lista de nós do caminho (start..alvo), ou None se não houver
    caminho dentro de `max_depth` saltos.
    """
    visited = {start.id}
    queue: deque[tuple[Node, list[Node]]] = deque([(start, [start])])

    while queue:
        node, path = queue.popleft()
        if len(path) - 1 >= max_depth:
            continue

        for kind in _EDGE_KINDS:
            for edge in store.get_outgoing_edges(node.id, kind=kind):
                target = store.get_node(edge.target_id)
                if target is None:
                    continue
                resolved = store.resolve_call_to_definition(target)
                if resolved.id in visited:
                    continue

                new_path = [*path, resolved]
                if resolved.name == target_name:
                    return new_path

                visited.add(resolved.id)
                queue.append((resolved, new_path))

    return None


def find_dependency_path(
    store: GraphStore,
    symbol_a: str,
    symbol_b: str,
    max_depth: int = 10,
) -> dict[str, Any]:
    """Acha o caminho de dependência entre dois símbolos.

    Tenta primeiro A → B (A depende de B); se não achar, tenta B → A. A
    direção encontrada é reportada — o caminho nunca é invertido
    artificialmente, pois isso implicaria arestas que não existem de fato.

    Returns:
        Dict com:
        - "found": bool.
        - "direction": "forward" (A depende de B), "backward" (B depende de
          A), ou None se não achou nenhuma das duas.
        - "path": lista de Node do caminho encontrado (vazia se not found).
        - "reason": mensagem quando found=False (símbolo não encontrado, ou
          nenhum caminho dentro de max_depth).
    """
    node_a = _resolve_symbol(store, symbol_a)
    node_b = _resolve_symbol(store, symbol_b)

    if node_a is None or node_b is None:
        missing = symbol_a if node_a is None else symbol_b
        return {"found": False, "direction": None, "path": [], "reason": f"Símbolo não encontrado: {missing}"}

    forward = _bfs_path(store, node_a, symbol_b, max_depth)
    if forward is not None:
        return {"found": True, "direction": "forward", "path": forward, "reason": ""}

    backward = _bfs_path(store, node_b, symbol_a, max_depth)
    if backward is not None:
        return {"found": True, "direction": "backward", "path": backward, "reason": ""}

    return {
        "found": False,
        "direction": None,
        "path": [],
        "reason": f"Nenhum caminho de dependência entre '{symbol_a}' e '{symbol_b}' em até {max_depth} saltos.",
    }
