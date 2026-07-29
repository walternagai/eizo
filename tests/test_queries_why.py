"""Testes para queries/why.py — caminho de dependência entre dois símbolos."""

from __future__ import annotations

from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore
from eizo.queries.why import find_dependency_path


class TestFindDependencyPath:
    """Testa find_dependency_path() contra um GraphStore construído à mão."""

    def _chain(self, store: GraphStore) -> None:
        """top -> middle -> bottom, mais isolated (sem arestas)."""
        store.upsert_nodes([
            Node(id="top", name="top", kind="function", file_path="a.py", language="python"),
            Node(id="middle", name="middle", kind="function", file_path="a.py", language="python"),
            Node(id="bottom", name="bottom", kind="function", file_path="a.py", language="python"),
            Node(id="isolated", name="isolated", kind="function", file_path="a.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="top", target_id="middle", kind="calls"),
            Edge(source_id="middle", target_id="bottom", kind="calls"),
        ])

    def test_forward_path_found(self, store: GraphStore) -> None:
        self._chain(store)
        result = find_dependency_path(store, "top", "bottom")
        assert result["found"] is True
        assert result["direction"] == "forward"
        assert [n.name for n in result["path"]] == ["top", "middle", "bottom"]

    def test_backward_path_found_when_only_reverse_exists(self, store: GraphStore) -> None:
        """Chamando why(bottom, top) — bottom não alcança top, mas top alcança bottom."""
        self._chain(store)
        result = find_dependency_path(store, "bottom", "top")
        assert result["found"] is True
        assert result["direction"] == "backward"
        # o caminho é sempre reportado na direção real das arestas (top -> bottom),
        # nunca invertido artificialmente
        assert [n.name for n in result["path"]] == ["top", "middle", "bottom"]

    def test_no_path_between_unconnected_symbols(self, store: GraphStore) -> None:
        self._chain(store)
        result = find_dependency_path(store, "top", "isolated")
        assert result["found"] is False
        assert result["direction"] is None
        assert result["path"] == []
        assert "isolated" in result["reason"]

    def test_unknown_symbol_a_reported(self, store: GraphStore) -> None:
        self._chain(store)
        result = find_dependency_path(store, "nao_existe", "top")
        assert result["found"] is False
        assert "nao_existe" in result["reason"]

    def test_unknown_symbol_b_reported(self, store: GraphStore) -> None:
        self._chain(store)
        result = find_dependency_path(store, "top", "nao_existe")
        assert result["found"] is False
        assert "nao_existe" in result["reason"]

    def test_bfs_finds_shortest_path(self, store: GraphStore) -> None:
        """Dois caminhos possíveis de A até D — BFS acha o mais curto (direto)."""
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="x.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="x.py", language="python"),
            Node(id="c", name="c", kind="function", file_path="x.py", language="python"),
            Node(id="d", name="d", kind="function", file_path="x.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="b", target_id="c", kind="calls"),
            Edge(source_id="c", target_id="d", kind="calls"),
            Edge(source_id="a", target_id="d", kind="calls"),  # atalho direto
        ])

        result = find_dependency_path(store, "a", "d")

        assert [n.name for n in result["path"]] == ["a", "d"]

    def test_max_depth_limits_search(self, store: GraphStore) -> None:
        """Caminho existe, mas fora do max_depth — não é encontrado."""
        self._chain(store)
        result = find_dependency_path(store, "top", "bottom", max_depth=1)
        assert result["found"] is False

    def test_respects_max_depth_when_within_range(self, store: GraphStore) -> None:
        self._chain(store)
        result = find_dependency_path(store, "top", "bottom", max_depth=2)
        assert result["found"] is True

    def test_follows_inherits_edges(self, store: GraphStore) -> None:
        """Caminho via herança (Child -> Base) também é encontrado."""
        store.upsert_nodes([
            Node(id="child", name="Child", kind="class", file_path="x.py", language="python"),
            Node(id="base", name="Base", kind="class", file_path="x.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="child", target_id="base", kind="inherits"),
        ])
        result = find_dependency_path(store, "Child", "Base")
        assert result["found"] is True
        assert [n.name for n in result["path"]] == ["Child", "Base"]

    def test_resolve_falls_back_to_non_definition_node(self, store: GraphStore) -> None:
        """Quando o único nó com o nome não é uma definição (só um call site
        homônimo), ainda resolve para ele em vez de tratar como não encontrado."""
        store.upsert_nodes([
            Node(id="caller", name="caller", kind="function", file_path="a.py", language="python"),
            Node(id="cs", name="orphan", kind="call", file_path="a.py", language="python"),
        ])
        store.upsert_edges([Edge(source_id="caller", target_id="cs", kind="calls")])

        result = find_dependency_path(store, "caller", "orphan")

        assert result["found"] is True

    def test_diamond_shape_revisits_intermediate_node_without_duplicating(self, store: GraphStore) -> None:
        """A -> B -> M e A -> C -> M, com M -> alvo: M é alcançado duas vezes
        (via B e via C) antes de ser processado — a segunda vez só marca
        "já visitado" e segue, sem reenfileirar."""
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="x.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="x.py", language="python"),
            Node(id="c", name="c", kind="function", file_path="x.py", language="python"),
            Node(id="m", name="m", kind="function", file_path="x.py", language="python"),
            Node(id="alvo", name="alvo", kind="function", file_path="x.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="a", target_id="c", kind="calls"),
            Edge(source_id="b", target_id="m", kind="calls"),
            Edge(source_id="c", target_id="m", kind="calls"),
            Edge(source_id="m", target_id="alvo", kind="calls"),
        ])

        result = find_dependency_path(store, "a", "alvo")

        assert result["found"] is True
        assert result["path"][-1].name == "alvo"
