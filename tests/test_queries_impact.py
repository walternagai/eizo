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

    def test_analyze_impact_transitive_inherits(self, store) -> None:
        """Cadeia de impacto aninhada via inherits (cobre linha 85)."""
        store.upsert_nodes([
            Node(id="base", name="Base", kind="class", file_path="base.py", language="python"),
            Node(id="child", name="Child", kind="class", file_path="child.py", language="python"),
            Node(id="grandchild", name="Grandchild", kind="class", file_path="gc.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="child", target_id="base", kind="inherits"),
            Edge(source_id="grandchild", target_id="child", kind="inherits"),
        ])

        result = analyze_impact(store, "Base")
        assert result["symbol"] is not None
        assert len(result["impact_chain"]) == 1
        entry = result["impact_chain"][0]
        assert entry["relation"] == "inherits"
        # child herda de base, e grandchild herda de child → dependents aninhado
        assert "dependents" in entry
        assert len(entry["dependents"]) == 1
        assert entry["dependents"][0]["relation"] == "inherits"

    def test_analyze_impact_transitive_calls(self, store) -> None:
        """Cadeia de impacto aninhada via calls (cobre linha 100)."""
        store.upsert_nodes([
            Node(id="callee", name="callee", kind="function", file_path="c.py", language="python"),
            Node(id="caller", name="caller", kind="function", file_path="cr.py", language="python"),
            Node(id="top_caller", name="top_caller", kind="function", file_path="tc.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="caller", target_id="callee", kind="calls"),
            Edge(source_id="top_caller", target_id="caller", kind="calls"),
        ])

        result = analyze_impact(store, "callee")
        assert result["symbol"] is not None
        assert len(result["impact_chain"]) == 1
        entry = result["impact_chain"][0]
        assert entry["relation"] == "calls"
        # caller chama callee, e top_caller chama caller → dependents aninhado
        assert "dependents" in entry
        assert len(entry["dependents"]) == 1
        assert entry["dependents"][0]["relation"] == "calls"


class TestImpactCallSiteResolution:
    """Testes para resolução de call sites no impacto (Fix B)."""

    def test_impact_finds_callers_via_call_sites(self, store) -> None:
        """analyze_impact deve encontrar callers de uma definição através
        de call sites com mesmo nome (Bug 2 do relatório)."""
        store.upsert_nodes([
            Node(id="defn", name="core", kind="function",
                 file_path="lib.py", language="python", line_start=50),
            Node(id="call_x", name="core", kind="call",
                 file_path="app.py", language="python", line_start=10),
            Node(id="app_fn", name="main", kind="function",
                 file_path="app.py", language="python", line_start=1),
        ])
        # Parser cria caller → call_site, não caller → definição
        store.upsert_edges([
            Edge(source_id="app_fn", target_id="call_x", kind="calls"),
        ])

        result = analyze_impact(store, "core")
        assert result["symbol"] is not None
        assert result["symbol"].id == "defn"
        relations = [item["relation"] for item in result["impact_chain"]]
        assert "calls" in relations
        callers = [item["node"].name for item in result["impact_chain"]
                   if item["relation"] == "calls"]
        assert "main" in callers

    def test_impact_prefers_definition_over_call_site(self, store) -> None:
        """Quando existem definição e call site com mesmo nome, impact
        deve analisar a definição, não o call site (Fix A)."""
        store.upsert_nodes([
            Node(id="defn", name="foo", kind="function",
                 file_path="lib.py", language="python", line_start=20),
            Node(id="call_x", name="foo", kind="call",
                 file_path="app.py", language="python", line_start=5),
        ])
        result = analyze_impact(store, "foo")
        assert result["symbol"] is not None
        assert result["symbol"].kind == "function"
        assert result["symbol"].id == "defn"

    def test_impact_dedup_direct_and_via_call_site(self, store) -> None:
        """Se o mesmo caller aparece via aresta direta e via call site,
        não deve duplicar."""
        store.upsert_nodes([
            Node(id="defn", name="baz", kind="function",
                 file_path="lib.py", language="python", line_start=10),
            Node(id="call_site", name="baz", kind="call",
                 file_path="a.py", language="python", line_start=5),
            Node(id="caller", name="uses", kind="function",
                 file_path="a.py", language="python", line_start=1),
        ])
        store.upsert_edges([
            Edge(source_id="caller", target_id="defn", kind="calls"),
            Edge(source_id="caller", target_id="call_site", kind="calls"),
        ])

        result = analyze_impact(store, "baz")
        assert result["symbol"] is not None
        call_entries = [item for item in result["impact_chain"]
                        if item["relation"] == "calls"]
        # Sem duplicação do mesmo caller
        assert len(call_entries) == 1
