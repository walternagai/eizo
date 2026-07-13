"""Testes para queries/impact.py."""

from __future__ import annotations

from eizo.graph.models import Edge, Node
from eizo.queries.impact import analyze_impact


class TestImpactQueries:
    """Testes para queries de impacto."""

    def test_analyze_impact_not_found(self, store) -> None:
        """Símbolo não encontrado."""
        result = analyze_impact(store, "nonexistent")
        assert result["symbol"] is None

    def test_analyze_impact_imports(self, store) -> None:
        """Impacto via imports."""
        store.upsert_nodes([
            Node(id="dep", name="dep", kind="function", file_path="dep.py", language="python"),
            Node(id="user1", name="user1", kind="function", file_path="a.py", language="python"),
            Node(id="user2", name="user2", kind="function", file_path="b.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="user1", target_id="dep", kind="imports"),
            Edge(source_id="user2", target_id="dep", kind="imports"),
        ])

        result = analyze_impact(store, "dep")
        assert result["symbol"] is not None
        assert len(result["impact_chain"]) == 2

    def test_analyze_impact_calls(self, store) -> None:
        """Impacto via chamadas."""
        store.upsert_nodes([
            Node(id="callee", name="callee", kind="function", file_path="callee.py", language="python"),
            Node(id="caller", name="caller", kind="function", file_path="caller.py", language="python"),
        ])
        store.upsert_edge(Edge(source_id="caller", target_id="callee", kind="calls"))

        result = analyze_impact(store, "callee")
        assert result["symbol"] is not None
        assert len(result["impact_chain"]) == 1
        assert result["impact_chain"][0]["relation"] == "calls"

    def test_analyze_impact_inheritance(self, store) -> None:
        """Impacto via herança."""
        store.upsert_nodes([
            Node(id="base", name="Base", kind="class", file_path="base.py", language="python"),
            Node(id="derived", name="Derived", kind="class", file_path="derived.py", language="python"),
        ])
        store.upsert_edge(Edge(source_id="derived", target_id="base", kind="inherits"))

        result = analyze_impact(store, "Base")
        assert result["symbol"] is not None
        assert len(result["impact_chain"]) == 1
        assert result["impact_chain"][0]["relation"] == "inherits"

    def test_analyze_impact_transitive(self, store) -> None:
        """Impacto transitivo (cadeia de dependentes)."""
        store.upsert_nodes([
            Node(id="core", name="core", kind="function", file_path="core.py", language="python"),
            Node(id="middle", name="middle", kind="function", file_path="middle.py", language="python"),
            Node(id="top", name="top", kind="function", file_path="top.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="middle", target_id="core", kind="imports"),
            Edge(source_id="top", target_id="middle", kind="imports"),
        ])

        result = analyze_impact(store, "core")
        assert result["symbol"] is not None
        assert len(result["impact_chain"]) == 1
        # middle depende de core, e top depende de middle
        assert "dependents" in result["impact_chain"][0]
