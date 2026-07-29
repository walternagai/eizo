"""Detecção de ciclos de import (dependência circular entre arquivos).

Constrói o grafo de imports em nível de arquivo (`GraphStore.get_file_import_graph`)
e roda Tarjan (SCC) sobre ele — um componente fortemente conexo com mais de um
nó, ou um nó com self-loop, é um ciclo de dependência real.
"""

from __future__ import annotations

from typing import Any

from eizo.graph.store import GraphStore


def _tarjan_scc(graph: dict[str, set[str]]) -> list[list[str]]:
    """Componentes fortemente conexos de `graph`, via Tarjan iterativo.

    Iterativo (não recursivo) para não estourar o limite de recursão do
    Python em cadeias de import profundas.
    """
    index_counter = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    result: list[list[str]] = []

    for start in graph:
        if start in indices:
            continue

        work_stack: list[tuple[str, list[str]]] = [(start, list(graph.get(start, ())))]
        indices[start] = lowlink[start] = index_counter
        index_counter += 1
        stack.append(start)
        on_stack.add(start)

        while work_stack:
            node, neighbors = work_stack[-1]
            if neighbors:
                neighbor = neighbors.pop()
                if neighbor not in indices:
                    indices[neighbor] = lowlink[neighbor] = index_counter
                    index_counter += 1
                    stack.append(neighbor)
                    on_stack.add(neighbor)
                    work_stack.append((neighbor, list(graph.get(neighbor, ()))))
                elif neighbor in on_stack:
                    lowlink[node] = min(lowlink[node], indices[neighbor])
            else:
                work_stack.pop()
                if work_stack:
                    parent = work_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                if lowlink[node] == indices[node]:
                    scc: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        scc.append(w)
                        if w == node:
                            break
                    result.append(scc)

    return result


def _find_one_cycle_path(scc: list[str], graph: dict[str, set[str]]) -> list[str]:
    """Acha um caminho concreto de ciclo dentro de um SCC via DFS restrito
    aos membros do grupo. Como o SCC é fortemente conexo por definição,
    sempre existe pelo menos um nó com aresta direta de volta a `start`."""
    scc_set = set(scc)
    start = scc[0]
    dfs_stack: list[tuple[str, list[str]]] = [(start, [start])]
    visited: set[str] = {start}
    while dfs_stack:
        node, path = dfs_stack.pop()
        for neighbor in graph.get(node, ()):
            if neighbor == start and len(path) > 1:
                return [*path, start]
            if neighbor in scc_set and neighbor not in visited:
                visited.add(neighbor)
                dfs_stack.append((neighbor, [*path, neighbor]))
    return [*scc, start]  # inalcançável para um SCC válido; fallback defensivo


def find_import_cycles(store: GraphStore) -> list[dict[str, Any]]:
    """Encontra ciclos de dependência entre arquivos via imports.

    Returns:
        Lista de dicts, um por ciclo, ordenada do maior grupo para o menor:
        - "files": arquivos que participam do ciclo (ordenados).
        - "path": um caminho concreto do ciclo (ex: [a, b, c, a]) para
          orientar qual import quebrar.
    """
    graph = store.get_file_import_graph()
    sccs = _tarjan_scc(graph)

    cycles: list[dict[str, Any]] = []
    for scc in sccs:
        if len(scc) > 1:
            cycles.append({"files": sorted(scc), "path": _find_one_cycle_path(scc, graph)})
        elif len(scc) == 1 and scc[0] in graph.get(scc[0], set()):
            cycles.append({"files": scc, "path": [scc[0], scc[0]]})

    cycles.sort(key=lambda c: (-len(c["files"]), c["files"][0]))
    return cycles
