"""Testes para queries/cycles.py — detecção de ciclos de import."""

from __future__ import annotations

from eizo.graph.models import Node
from eizo.graph.store import GraphStore
from eizo.queries.cycles import _find_one_cycle_path, _tarjan_scc, find_import_cycles


class TestTarjanScc:
    """Testa _tarjan_scc() com grafos sintéticos."""

    def test_simple_cycle(self) -> None:
        graph = {"A": {"B"}, "B": {"C"}, "C": {"A"}, "D": set()}
        sccs = {frozenset(s) for s in _tarjan_scc(graph)}
        assert frozenset({"A", "B", "C"}) in sccs
        assert frozenset({"D"}) in sccs

    def test_dag_has_no_multi_node_scc(self) -> None:
        """Um DAG (sem ciclos) só produz SCCs de tamanho 1."""
        graph = {"A": {"B"}, "B": {"C"}, "C": set()}
        sccs = _tarjan_scc(graph)
        assert all(len(s) == 1 for s in sccs)

    def test_self_loop(self) -> None:
        graph = {"A": {"A"}}
        sccs = _tarjan_scc(graph)
        assert sccs == [["A"]]

    def test_two_independent_cycles(self) -> None:
        graph = {"A": {"B"}, "B": {"A"}, "C": {"D"}, "D": {"C"}}
        sccs = {frozenset(s) for s in _tarjan_scc(graph) if len(s) > 1}
        assert sccs == {frozenset({"A", "B"}), frozenset({"C", "D"})}

    def test_empty_graph(self) -> None:
        assert _tarjan_scc({}) == []

    def test_deep_chain_does_not_recurse_stack_overflow(self) -> None:
        """Cadeia de imports profunda (sem ciclo) não estoura RecursionError.

        Regressão-alvo: implementação recursiva de Tarjan estouraria o
        limite de recursão do Python (~1000) numa cadeia deste tamanho.
        """
        n = 3000
        graph = {str(i): {str(i + 1)} for i in range(n)}
        graph[str(n)] = set()
        sccs = _tarjan_scc(graph)
        assert all(len(s) == 1 for s in sccs)
        assert len(sccs) == n + 1


class TestFindOneCyclePath:
    """Testa _find_one_cycle_path()."""

    def test_returns_path_back_to_start(self) -> None:
        graph = {"A": {"B"}, "B": {"C"}, "C": {"A"}}
        path = _find_one_cycle_path(["A", "B", "C"], graph)
        assert path[0] == path[-1]
        assert set(path[:-1]) == {"A", "B", "C"}
        # cada passo consecutivo do caminho é uma aresta real do grafo
        for a, b in zip(path, path[1:], strict=False):
            assert b in graph[a]

    def test_two_node_cycle(self) -> None:
        graph = {"A": {"B"}, "B": {"A"}}
        path = _find_one_cycle_path(["A", "B"], graph)
        assert path[0] == path[-1]
        assert set(path[:-1]) == {"A", "B"}


class TestFindImportCycles:
    """Testa find_import_cycles() contra um GraphStore real."""

    def _file_node(self, path: str) -> Node:
        return Node(id=f"file:{path}", name=path, kind="file", file_path=path, language="python")

    def _import_node(self, id_: str, module_hint: str, in_file: str) -> Node:
        return Node(id=id_, name=module_hint, kind="import", file_path=in_file, language="python")

    def test_detects_two_file_cycle(self, store: GraphStore) -> None:
        """a.py importa b, b.py importa a — ciclo de 2 arquivos."""
        store.upsert_nodes([
            self._file_node("a.py"),
            self._file_node("b.py"),
            self._file_node("c.py"),
            self._import_node("i1", "b", "a.py"),
            self._import_node("i2", "a", "b.py"),
        ])

        cycles = find_import_cycles(store)

        assert len(cycles) == 1
        assert cycles[0]["files"] == ["a.py", "b.py"]
        assert cycles[0]["path"][0] == cycles[0]["path"][-1]

    def test_no_cycle_returns_empty(self, store: GraphStore) -> None:
        """a.py importa b.py, sem retorno — nenhum ciclo."""
        store.upsert_nodes([
            self._file_node("a.py"),
            self._file_node("b.py"),
            self._import_node("i1", "b", "a.py"),
        ])

        assert find_import_cycles(store) == []

    def test_empty_graph_returns_empty(self, store: GraphStore) -> None:
        assert find_import_cycles(store) == []

    def test_self_import_is_not_flagged_as_cycle(self, store: GraphStore) -> None:
        """Um import cujo module_hint bate com o próprio arquivo não conta.

        `get_file_import_graph` exclui esse auto-match deliberadamente: a
        heurística de module_hint é best-effort (só compara o stem do nome),
        e um arquivo "importando a si mesmo" quase sempre é o próprio
        artefato da heurística, não um ciclo real.
        """
        store.upsert_nodes([
            self._file_node("a.py"),
            self._import_node("i1", "a", "a.py"),
        ])

        assert find_import_cycles(store) == []

    def test_three_file_cycle(self, store: GraphStore) -> None:
        """a -> b -> c -> a."""
        store.upsert_nodes([
            self._file_node("a.py"),
            self._file_node("b.py"),
            self._file_node("c.py"),
            self._import_node("i1", "b", "a.py"),
            self._import_node("i2", "c", "b.py"),
            self._import_node("i3", "a", "c.py"),
        ])

        cycles = find_import_cycles(store)

        assert len(cycles) == 1
        assert cycles[0]["files"] == ["a.py", "b.py", "c.py"]
