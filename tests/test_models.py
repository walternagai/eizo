"""Testes para graph/models.py."""

from __future__ import annotations

from eizo.graph.models import Edge, GraphStats, Node


class TestNode:
    """Testes para a dataclass Node."""

    def test_create_node(self) -> None:
        """Cria um nó com atributos básicos."""
        node = Node(
            id="abc123",
            name="minha_funcao",
            kind="function",
            file_path="/projeto/main.py",
            language="python",
            line_start=10,
            line_end=25,
        )
        assert node.id == "abc123"
        assert node.name == "minha_funcao"
        assert node.kind == "function"
        assert node.language == "python"
        assert node.line_start == 10
        assert node.line_end == 25

    def test_node_with_optional_fields(self) -> None:
        """Cria um nó com campos opcionais."""
        node = Node(
            id="def456",
            name="MinhaClasse",
            kind="class",
            file_path="/projeto/model.py",
            language="python",
            docstring="Classe de exemplo",
            code_snippet="class MinhaClasse: ...",
            metadata={"abstract": True},
        )
        assert node.docstring == "Classe de exemplo"
        assert node.metadata["abstract"] is True

    def test_node_default_metadata(self) -> None:
        """Metadata deve ser dict vazio por padrão."""
        node = Node(
            id="ghi789",
            name="foo",
            kind="function",
            file_path="/projeto/foo.py",
            language="python",
        )
        assert node.metadata == {}


class TestEdge:
    """Testes para a dataclass Edge."""

    def test_create_edge(self) -> None:
        """Cria uma aresta com atributos básicos."""
        edge = Edge(
            source_id="abc123",
            target_id="def456",
            kind="calls",
        )
        assert edge.source_id == "abc123"
        assert edge.target_id == "def456"
        assert edge.kind == "calls"

    def test_edge_with_metadata(self) -> None:
        """Cria uma aresta com metadados."""
        edge = Edge(
            source_id="abc123",
            target_id="def456",
            kind="imports",
            metadata={"module": "os"},
        )
        assert edge.metadata["module"] == "os"


class TestGraphStats:
    """Testes para a dataclass GraphStats."""

    def test_default_stats(self) -> None:
        """Estatísticas devem começar zeradas."""
        stats = GraphStats()
        assert stats.total_nodes == 0
        assert stats.total_edges == 0
        assert stats.by_language == {}
        assert stats.by_kind == {}
        assert stats.by_edge_kind == {}
        assert stats.total_files == 0
        assert stats.db_size_bytes == 0
