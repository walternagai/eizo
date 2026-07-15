"""Testes estendidos para queries — edge cases, depth > 1."""

from __future__ import annotations

from eizo.graph.models import Edge, Node
from eizo.queries.impact import analyze_impact
from eizo.queries.search import get_symbol_context, search_symbols
from eizo.queries.trace import trace_call_path


class TestSearchQueriesExtended:
    """Testes estendidos para queries de busca."""

    def test_search_symbols_empty_db(self, store) -> None:
        """Busca em banco vazio."""
        results = search_symbols(store, "anything")
        assert results == []

    def test_search_symbols_limit(self, store) -> None:
        """Limite de resultados."""
        nodes = [
            Node(id=f"n{i}", name=f"func{i}", kind="function",
                 file_path="a.py", language="python")
            for i in range(10)
        ]
        store.upsert_nodes(nodes)
        results = search_symbols(store, "func", limit=3)
        assert len(results) == 3

    def test_get_symbol_context_depth2_no_edges(self, store) -> None:
        """Contexto com depth=2 mas sem arestas."""
        store.upsert_node(Node(id="a", name="a", kind="function", file_path="a.py", language="python"))
        context = get_symbol_context(store, "a", depth=2)
        assert context["node"] is not None
        assert "deeper_incoming" in context
        assert "deeper_outgoing" in context

    def test_get_symbol_context_depth2_with_edges(self, store) -> None:
        """Contexto com depth=2 e arestas."""
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="a.py", language="python"),
            Node(id="c", name="c", kind="function", file_path="a.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="b", target_id="c", kind="calls"),
        ])
        context = get_symbol_context(store, "a", depth=2)
        assert "deeper_outgoing" in context
        # deeper deve incluir c via b
        assert len(context["deeper_outgoing"]) >= 1


class TestTraceQueriesExtended:
    """Testes estendidos para queries de trace."""

    def test_trace_call_path_empty_db(self, store) -> None:
        """Trace em banco vazio."""
        result = trace_call_path(store, "anything")
        assert result["symbol"] is None

    def test_trace_call_path_max_depth(self, store) -> None:
        """Trace com profundidade limitada."""
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
            Node(id="c", name="c", kind="function", file_path="c.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="b", target_id="c", kind="calls"),
        ])
        result = trace_call_path(store, "a", direction="outgoing", max_depth=1)
        assert result["symbol"] is not None
        assert len(result["callees"]) == 1  # só b, c está a depth 2

    def test_trace_call_path_cycle(self, store) -> None:
        """Trace com ciclo não deve entrar em loop infinito."""
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="b", target_id="a", kind="calls"),
        ])
        result = trace_call_path(store, "a", direction="both", max_depth=5)
        assert result["symbol"] is not None
        # Não deve crashar por ciclo


class TestImpactQueriesExtended:
    """Testes estendidos para queries de impacto."""

    def test_analyze_impact_empty_db(self, store) -> None:
        """Impact em banco vazio."""
        result = analyze_impact(store, "anything")
        assert result["symbol"] is None

    def test_analyze_impact_no_dependents(self, store) -> None:
        """Símbolo sem dependentes."""
        store.upsert_node(Node(id="a", name="a", kind="function", file_path="a.py", language="python"))
        result = analyze_impact(store, "a")
        assert result["symbol"] is not None
        assert result["impact_chain"] == []

    def test_analyze_impact_multiple_relations(self, store) -> None:
        """Impact com múltiplos tipos de relação."""
        store.upsert_nodes([
            Node(id="core", name="core", kind="function", file_path="core.py", language="python"),
            Node(id="importer", name="importer", kind="function", file_path="a.py", language="python"),
            Node(id="caller", name="caller", kind="function", file_path="b.py", language="python"),
            Node(id="child", name="Child", kind="class", file_path="c.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="importer", target_id="core", kind="imports"),
            Edge(source_id="caller", target_id="core", kind="calls"),
            Edge(source_id="child", target_id="core", kind="inherits"),
        ])
        result = analyze_impact(store, "core")
        assert result["symbol"] is not None
        assert len(result["impact_chain"]) == 3
        relations = {item["relation"] for item in result["impact_chain"]}
        assert relations == {"imports", "calls", "inherits"}

    def test_analyze_impact_max_depth(self, store) -> None:
        """Impact com profundidade limitada."""
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
            Node(id="c", name="c", kind="function", file_path="c.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="b", target_id="a", kind="imports"),
            Edge(source_id="c", target_id="b", kind="imports"),
        ])
        result = analyze_impact(store, "a", max_depth=1)
        assert result["symbol"] is not None
        assert len(result["impact_chain"]) == 1  # só b
        assert "dependents" not in result["impact_chain"][0]
