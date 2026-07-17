"""Testes para queries/search.py."""

from __future__ import annotations

from eizo.graph.models import Edge, Node
from eizo.queries.search import get_symbol_context, search_symbols


class TestSearchQueries:
    """Testes para queries de busca."""

    def test_search_symbols(self, store) -> None:
        """Busca símbolos por nome."""
        store.upsert_nodes([
            Node(id="a1", name="get_user", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="get_item", kind="function", file_path="b.py", language="python"),
            Node(id="a3", name="UserModel", kind="class", file_path="c.py", language="python"),
        ])

        results = search_symbols(store, "get")
        assert len(results) == 2

    def test_search_symbols_with_filters(self, store) -> None:
        """Busca com filtros."""
        store.upsert_nodes([
            Node(id="a1", name="helper", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="helper", kind="function", file_path="b.ts", language="typescript"),
        ])

        results = search_symbols(store, "helper", language="python")
        assert len(results) == 1
        assert results[0].language == "python"

    def test_search_symbols_full_text_matches_docstring(self, store) -> None:
        """full_text=True busca em docstring/code_snippet, não só no nome."""
        store.upsert_nodes([
            Node(
                id="a1", name="process", kind="function", file_path="a.py", language="python",
                docstring="Valida um pagamento antes de processar.",
            ),
            Node(id="a2", name="other", kind="function", file_path="b.py", language="python"),
        ])

        # LIKE por nome não encontra "pagamento" (não está no nome).
        assert search_symbols(store, "pagamento") == []

        results = search_symbols(store, "pagamento", full_text=True)
        assert len(results) == 1
        assert results[0].id == "a1"

    def test_search_symbols_full_text_default_off(self, store) -> None:
        """Sem full_text, comportamento é o de busca por nome (LIKE) como antes."""
        store.upsert_nodes([
            Node(id="a1", name="get_user", kind="function", file_path="a.py", language="python"),
        ])
        results = search_symbols(store, "get")
        assert len(results) == 1
        assert results[0].id == "a1"

    def test_get_symbol_context(self, store) -> None:
        """Contexto de símbolo com vizinhança."""
        store.upsert_nodes([
            Node(id="caller", name="caller", kind="function", file_path="a.py", language="python"),
            Node(id="callee", name="callee", kind="function", file_path="a.py", language="python"),
        ])
        store.upsert_edge(Edge(source_id="caller", target_id="callee", kind="calls"))

        context = get_symbol_context(store, "caller")
        assert context["node"] is not None
        assert context["node"].name == "caller"
        assert len(context["outgoing"]) == 1
        assert len(context["file_nodes"]) == 2

    def test_get_symbol_context_not_found(self, store) -> None:
        """Contexto de símbolo inexistente."""
        context = get_symbol_context(store, "nonexistent")
        assert context["node"] is None
        assert context["incoming"] == []
        assert context["outgoing"] == []

    def test_get_symbol_context_depth2(self, store) -> None:
        """Contexto com profundidade 2."""
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
