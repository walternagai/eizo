"""Testes para queries/metrics.py — fan-in, fan-out e LOC por símbolo."""

from __future__ import annotations

from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore
from eizo.queries.metrics import compute_symbol_metrics


class TestComputeSymbolMetrics:
    """Testa compute_symbol_metrics() contra um GraphStore construído à mão."""

    def test_fan_in_counts_distinct_callers(self, store: GraphStore) -> None:
        """Duas chamadas do MESMO caller contam como 1 referência (dedup)."""
        store.upsert_nodes([
            Node(id="target", name="helper", kind="function", file_path="lib.py", language="python",
                 line_start=1, line_end=2),
            Node(id="caller", name="run", kind="function", file_path="main.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="caller", target_id="target", kind="calls"),
        ])

        results = compute_symbol_metrics(store, "helper")

        assert len(results) == 1
        assert results[0]["fan_in"] == 1

    def test_fan_out_counts_distinct_targets(self, store: GraphStore) -> None:
        """run() chama helper() duas vezes e outra() uma vez — fan_out=2 (distintos)."""
        store.upsert_nodes([
            Node(id="run", name="run", kind="function", file_path="main.py", language="python",
                 line_start=1, line_end=5),
            Node(id="helper", name="helper", kind="function", file_path="lib.py", language="python"),
            Node(id="outra", name="outra", kind="function", file_path="lib.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="run", target_id="helper", kind="calls"),
            Edge(source_id="run", target_id="outra", kind="calls"),
        ])

        results = compute_symbol_metrics(store, "run")

        assert results[0]["fan_out"] == 2

    def test_loc_computed_from_line_range(self, store: GraphStore) -> None:
        store.upsert_node(
            Node(id="f", name="f", kind="function", file_path="a.py", language="python",
                 line_start=10, line_end=15)
        )
        results = compute_symbol_metrics(store, "f")
        assert results[0]["loc"] == 6  # inclusive: 10..15

    def test_loc_none_when_lines_missing(self, store: GraphStore) -> None:
        store.upsert_node(
            Node(id="f", name="f", kind="function", file_path="a.py", language="python")
        )
        results = compute_symbol_metrics(store, "f")
        assert results[0]["loc"] is None

    def test_multiple_homonymous_definitions_all_returned(self, store: GraphStore) -> None:
        """Duas funções com o mesmo nome, em arquivos diferentes — ambas aparecem."""
        store.upsert_nodes([
            Node(id="f1", name="helper", kind="function", file_path="a.py", language="python"),
            Node(id="f2", name="helper", kind="function", file_path="b.py", language="python"),
        ])
        results = compute_symbol_metrics(store, "helper")
        assert {r["node"].file_path for r in results} == {"a.py", "b.py"}

    def test_excludes_external_stub_from_candidates(self, store: GraphStore) -> None:
        """Stub externo de herança (metadata.external=True) não é uma definição real.

        Achado ao verificar manualmente: `class Child(Base)` cria um stub
        'Base' externo além da definição real — sem excluir, 'Base' aparecia
        duas vezes (a real e o stub) em compute_symbol_metrics.
        """
        store.upsert_nodes([
            Node(id="real", name="Base", kind="class", file_path="lib.py", language="python",
                 line_start=1, line_end=2),
            Node(id="child", name="Child", kind="class", file_path="lib.py", language="python"),
            Node(id="stub", name="Base", kind="class", file_path="lib.py", language="python",
                 metadata={"external": True}),
        ])
        store.upsert_edges([
            Edge(source_id="child", target_id="stub", kind="inherits"),
        ])

        results = compute_symbol_metrics(store, "Base")

        assert len(results) == 1
        assert results[0]["node"].id == "real"

    def test_excludes_non_definition_kinds(self, store: GraphStore) -> None:
        """Nós kind='call' ou 'import' homônimos não entram como candidatos."""
        store.upsert_nodes([
            Node(id="def1", name="helper", kind="function", file_path="a.py", language="python"),
            Node(id="call1", name="helper", kind="call", file_path="b.py", language="python"),
        ])
        results = compute_symbol_metrics(store, "helper")
        assert len(results) == 1
        assert results[0]["node"].kind == "function"

    def test_symbol_not_found_returns_empty(self, store: GraphStore) -> None:
        assert compute_symbol_metrics(store, "nao_existe") == []
