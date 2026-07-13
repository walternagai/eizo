"""Testes para queries/trace.py."""

from __future__ import annotations

from eizo.graph.models import Edge, Node
from eizo.queries.trace import trace_call_path


class TestTraceQueries:
    """Testes para queries de trace."""

    def test_trace_call_path_not_found(self, store) -> None:
        """Símbolo não encontrado."""
        result = trace_call_path(store, "nonexistent")
        assert result["symbol"] is None

    def test_trace_call_path_outgoing(self, store) -> None:
        """Traça chamadas que saem de um símbolo."""
        store.upsert_nodes([
            Node(id="caller", name="caller", kind="function", file_path="a.py", language="python"),
            Node(id="callee1", name="callee1", kind="function", file_path="b.py", language="python"),
            Node(id="callee2", name="callee2", kind="function", file_path="c.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="caller", target_id="callee1", kind="calls"),
            Edge(source_id="caller", target_id="callee2", kind="calls"),
        ])

        result = trace_call_path(store, "caller", direction="outgoing")
        assert result["symbol"] is not None
        assert len(result["callees"]) == 2

    def test_trace_call_path_incoming(self, store) -> None:
        """Traça chamadas que chegam em um símbolo."""
        store.upsert_nodes([
            Node(id="caller1", name="caller1", kind="function", file_path="a.py", language="python"),
            Node(id="caller2", name="caller2", kind="function", file_path="b.py", language="python"),
            Node(id="callee", name="callee", kind="function", file_path="c.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="caller1", target_id="callee", kind="calls"),
            Edge(source_id="caller2", target_id="callee", kind="calls"),
        ])

        result = trace_call_path(store, "callee", direction="incoming")
        assert result["symbol"] is not None
        assert len(result["callers"]) == 2

    def test_trace_call_path_both(self, store) -> None:
        """Traça ambas as direções."""
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
            Node(id="c", name="c", kind="function", file_path="c.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="b", target_id="c", kind="calls"),
        ])

        result = trace_call_path(store, "b", direction="both")
        assert result["symbol"] is not None
        assert len(result["callers"]) >= 1
        assert len(result["callees"]) >= 1
