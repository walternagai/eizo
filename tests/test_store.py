"""Testes para graph/store.py."""

from __future__ import annotations

from eizo.graph.models import Edge, Node


class TestGraphStore:
    """Testes para GraphStore."""

    def test_upsert_and_get_node(self, store) -> None:
        """Insere e recupera um nó."""
        node = Node(
            id="test1",
            name="minha_funcao",
            kind="function",
            file_path="/projeto/main.py",
            language="python",
            line_start=10,
            line_end=25,
        )
        store.upsert_node(node)

        retrieved = store.get_node("test1")
        assert retrieved is not None
        assert retrieved.name == "minha_funcao"
        assert retrieved.kind == "function"

    def test_upsert_node_updates_existing(self, store) -> None:
        """Atualizar nó existente deve sobrescrever."""
        node1 = Node(
            id="test1",
            name="foo",
            kind="function",
            file_path="/projeto/main.py",
            language="python",
        )
        store.upsert_node(node1)

        node2 = Node(
            id="test1",
            name="foo_updated",
            kind="function",
            file_path="/projeto/main.py",
            language="python",
        )
        store.upsert_node(node2)

        retrieved = store.get_node("test1")
        assert retrieved is not None
        assert retrieved.name == "foo_updated"

    def test_search_nodes(self, store) -> None:
        """Busca nós por nome."""
        nodes = [
            Node(id="a1", name="get_user", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="get_item", kind="function", file_path="b.py", language="python"),
            Node(id="a3", name="UserModel", kind="class", file_path="c.py", language="python"),
        ]
        store.upsert_nodes(nodes)

        results = store.search_nodes("get")
        assert len(results) == 2

        results = store.search_nodes("get", kind="class")
        assert len(results) == 0

        results = store.search_nodes("User")
        # LIKE é case-insensitive, então "User" também casa "get_user"
        assert len(results) == 2

    def test_search_nodes_with_filters(self, store) -> None:
        """Busca com filtros de tipo e linguagem."""
        nodes = [
            Node(id="a1", name="helper", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="helper", kind="function", file_path="b.ts", language="typescript"),
            Node(id="a3", name="Helper", kind="class", file_path="c.ts", language="typescript"),
        ]
        store.upsert_nodes(nodes)

        results = store.search_nodes("helper", language="python")
        assert len(results) == 1
        assert results[0].language == "python"

        results = store.search_nodes("helper", kind="class")
        # LIKE é case-insensitive, "Helper" casa com "helper"
        assert len(results) == 1

    def test_get_nodes_by_file(self, store) -> None:
        """Retorna nós de um arquivo específico."""
        nodes = [
            Node(id="a1", name="foo", kind="function", file_path="main.py", language="python"),
            Node(id="a2", name="bar", kind="function", file_path="main.py", language="python"),
            Node(id="a3", name="baz", kind="function", file_path="other.py", language="python"),
        ]
        store.upsert_nodes(nodes)

        results = store.get_nodes_by_file("main.py")
        assert len(results) == 2

    def test_delete_nodes_by_file(self, store) -> None:
        """Remove nós de um arquivo."""
        nodes = [
            Node(id="a1", name="foo", kind="function", file_path="main.py", language="python"),
            Node(id="a2", name="bar", kind="function", file_path="main.py", language="python"),
        ]
        store.upsert_nodes(nodes)
        store.delete_nodes_by_file("main.py")

        assert store.get_node("a1") is None
        assert store.get_node("a2") is None

    def test_upsert_edge(self, store) -> None:
        """Insere e recupera arestas."""
        store.upsert_node(Node(id="src", name="caller", kind="function", file_path="a.py", language="python"))
        store.upsert_node(Node(id="tgt", name="callee", kind="function", file_path="b.py", language="python"))

        edge = Edge(source_id="src", target_id="tgt", kind="calls")
        store.upsert_edge(edge)

        outgoing = store.get_outgoing_edges("src")
        assert len(outgoing) == 1
        assert outgoing[0].target_id == "tgt"

        incoming = store.get_incoming_edges("tgt")
        assert len(incoming) == 1
        assert incoming[0].source_id == "src"

    def test_get_outgoing_edges_filtered(self, store) -> None:
        """Filtra arestas por tipo."""
        store.upsert_node(Node(id="src", name="caller", kind="function", file_path="a.py", language="python"))
        store.upsert_node(Node(id="t1", name="callee1", kind="function", file_path="b.py", language="python"))
        store.upsert_node(Node(id="t2", name="callee2", kind="function", file_path="c.py", language="python"))

        store.upsert_edges([
            Edge(source_id="src", target_id="t1", kind="calls"),
            Edge(source_id="src", target_id="t2", kind="imports"),
        ])

        calls = store.get_outgoing_edges("src", kind="calls")
        assert len(calls) == 1

        imports = store.get_outgoing_edges("src", kind="imports")
        assert len(imports) == 1

    def test_get_stats_empty(self, store) -> None:
        """Estatísticas de grafo vazio."""
        stats = store.get_stats()
        assert stats.total_nodes == 0
        assert stats.total_edges == 0

    def test_get_stats_populated(self, store) -> None:
        """Estatísticas de grafo populado."""
        store.upsert_nodes([
            Node(id="a1", name="foo", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="bar", kind="class", file_path="a.py", language="python"),
            Node(id="a3", name="baz", kind="function", file_path="b.ts", language="typescript"),
        ])
        store.upsert_edges([
            Edge(source_id="a1", target_id="a2", kind="calls"),
        ])

        stats = store.get_stats()
        assert stats.total_nodes == 3
        assert stats.total_edges == 1
        assert stats.by_language["python"] == 2
        assert stats.by_language["typescript"] == 1
        assert stats.by_kind["function"] == 2
        assert stats.by_kind["class"] == 1
        assert stats.total_files == 2

    def test_clear_all(self, store) -> None:
        """Limpa todo o grafo."""
        store.upsert_node(Node(id="a1", name="foo", kind="function", file_path="a.py", language="python"))
        store.upsert_edge(Edge(source_id="a1", target_id="a1", kind="calls"))

        store.clear_all()
        stats = store.get_stats()
        assert stats.total_nodes == 0
        assert stats.total_edges == 0
