"""Testes estendidos para GraphStore — close, edge cases."""

from __future__ import annotations

from eizo.graph.models import Edge, Node


class TestGraphStoreExtended:
    """Testes estendidos para GraphStore."""

    def test_close(self, store) -> None:
        """close() deve fechar a conexão."""
        # Acessa conn para abrir
        conn = store.conn
        assert conn is not None
        store.close()
        # Após close, conn deve ser None
        assert store._conn is None  # noqa: SLF001

    def test_close_idempotent(self, store) -> None:
        """close() múltiplas vezes não deve crashar."""
        store.close()
        store.close()  # segunda vez

    def test_upsert_node_with_full_metadata(self, store) -> None:
        """Nó com metadados complexos."""
        node = Node(
            id="complex",
            name="ComplexNode",
            kind="class",
            file_path="/proj/model.py",
            language="python",
            line_start=1,
            line_end=100,
            docstring="Classe complexa",
            code_snippet="class ComplexNode: ...",
            metadata={"abstract": True, "decorators": ["@dataclass"]},
        )
        store.upsert_node(node)
        retrieved = store.get_node("complex")
        assert retrieved is not None
        assert retrieved.metadata["abstract"] is True
        assert retrieved.metadata["decorators"] == ["@dataclass"]

    def test_upsert_edges_batch(self, store) -> None:
        """Inserção em lote de arestas."""
        store.upsert_node(Node(id="a", name="a", kind="function", file_path="a.py", language="python"))
        store.upsert_node(Node(id="b", name="b", kind="function", file_path="b.py", language="python"))
        store.upsert_node(Node(id="c", name="c", kind="function", file_path="c.py", language="python"))

        edges = [
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="a", target_id="c", kind="calls"),
            Edge(source_id="b", target_id="c", kind="imports"),
        ]
        store.upsert_edges(edges)

        assert len(store.get_outgoing_edges("a")) == 2
        assert len(store.get_outgoing_edges("b")) == 1
        assert len(store.get_incoming_edges("c")) == 2

    def test_get_outgoing_edges_none(self, store) -> None:
        """Nó sem arestas de saída."""
        store.upsert_node(Node(id="a", name="a", kind="function", file_path="a.py", language="python"))
        assert store.get_outgoing_edges("a") == []

    def test_get_incoming_edges_none(self, store) -> None:
        """Nó sem arestas de entrada."""
        store.upsert_node(Node(id="a", name="a", kind="function", file_path="a.py", language="python"))
        assert store.get_incoming_edges("a") == []

    def test_get_node_not_found(self, store) -> None:
        """Nó inexistente retorna None."""
        assert store.get_node("nonexistent") is None

    def test_get_nodes_by_file_empty(self, store) -> None:
        """Arquivo sem nós."""
        assert store.get_nodes_by_file("nonexistent.py") == []

    def test_delete_nodes_by_file_nonexistent(self, store) -> None:
        """Deletar arquivo inexistente não crasha."""
        store.delete_nodes_by_file("nonexistent.py")  # não deve crashar

    def test_clear_all_empty(self, store) -> None:
        """Limpar grafo vazio não crasha."""
        store.clear_all()
        stats = store.get_stats()
        assert stats.total_nodes == 0

    def test_get_stats_with_edge_kinds(self, store) -> None:
        """Estatísticas com múltiplos tipos de aresta."""
        store.upsert_node(Node(id="a", name="a", kind="function", file_path="a.py", language="python"))
        store.upsert_node(Node(id="b", name="b", kind="function", file_path="b.py", language="python"))
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="a", target_id="b", kind="imports"),
        ])
        stats = store.get_stats()
        assert stats.by_edge_kind["calls"] == 1
        assert stats.by_edge_kind["imports"] == 1

    def test_get_nodes_by_name_exact(self, store) -> None:
        """get_nodes_by_name retorna apenas matches exatos."""
        store.upsert_nodes([
            Node(id="a1", name="foo", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="foobar", kind="function", file_path="b.py", language="python"),
            Node(id="a3", name="foo", kind="call", file_path="c.py", language="python"),
        ])
        results = store.get_nodes_by_name("foo")
        assert len(results) == 2
        assert all(r.name == "foo" for r in results)

    def test_get_nodes_by_name_with_kind_filter(self, store) -> None:
        """get_nodes_by_name filtra por kind."""
        store.upsert_nodes([
            Node(id="a1", name="foo", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="foo", kind="call", file_path="c.py", language="python"),
        ])
        results = store.get_nodes_by_name("foo", kind="call")
        assert len(results) == 1
        assert results[0].kind == "call"

    def test_get_nodes_by_name_no_match(self, store) -> None:
        """get_nodes_by_name sem matches retorna lista vazia."""
        store.upsert_node(Node(id="a", name="foo", kind="function",
                               file_path="a.py", language="python"))
        assert store.get_nodes_by_name("bar") == []

    def test_search_nodes_prioritizes_definition_over_call(self, store) -> None:
        """search_nodes deve ordenar definições antes de call sites (Fix A)."""
        store.upsert_nodes([
            Node(id="call_x", name="foo", kind="call",
                 file_path="a.py", language="python", line_start=5),
            Node(id="func_def", name="foo", kind="function",
                 file_path="lib.py", language="python", line_start=20),
        ])
        results = store.search_nodes("foo")
        assert len(results) == 2
        # Definição primeiro
        assert results[0].kind == "function"
        assert results[1].kind == "call"

    def test_search_nodes_exact_match_first(self, store) -> None:
        """search_nodes prioriza match exato sobre substring."""
        store.upsert_nodes([
            Node(id="a1", name="foobar", kind="function",
                 file_path="a.py", language="python"),
            Node(id="a2", name="foo", kind="function",
                 file_path="b.py", language="python"),
        ])
        results = store.search_nodes("foo")
        assert len(results) == 2
        # Match exato primeiro
        assert results[0].name == "foo"
        assert results[1].name == "foobar"
