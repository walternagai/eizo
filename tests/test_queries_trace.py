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

    def test_trace_incoming_excludes_non_call_references(self, store) -> None:
        """Trace incoming só considera relação 'calls' — imports não contam
        como caller (get_real_references retorna outras kinds também)."""
        store.upsert_nodes([
            Node(id="importer", name="importer", kind="function", file_path="a.py", language="python"),
            Node(id="caller", name="caller", kind="function", file_path="b.py", language="python"),
            Node(id="callee", name="callee", kind="function", file_path="c.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="importer", target_id="callee", kind="imports"),
            Edge(source_id="caller", target_id="callee", kind="calls"),
        ])

        result = trace_call_path(store, "callee", direction="incoming")
        callers = {c["node"].name for c in result["callers"]}
        assert callers == {"caller"}

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

    def test_trace_per_branch_visited(self, store) -> None:
        """Losango A->B, A->C, B->D, C->D: D deve aparecer em ambos os ramos.

        Com visited compartilhado (bug antigo), D apareceria apenas no primeiro
        ramo visitado. Com per-branch visited, D aparece nos dois.
        """
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
            Node(id="c", name="c", kind="function", file_path="c.py", language="python"),
            Node(id="d", name="d", kind="function", file_path="d.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="a", target_id="c", kind="calls"),
            Edge(source_id="b", target_id="d", kind="calls"),
            Edge(source_id="c", target_id="d", kind="calls"),
        ])

        result = trace_call_path(store, "a", direction="outgoing", max_depth=5)
        callees = result["callees"]
        assert len(callees) == 2  # B e C no nível 1

        # Cada ramo (B e C) deve ter D como callee
        names_by_branch = {b["node"].name: b for b in callees}
        assert "b" in names_by_branch
        assert "c" in names_by_branch
        assert "callees" in names_by_branch["b"]
        assert "callees" in names_by_branch["c"]
        assert names_by_branch["b"]["callees"][0]["node"].name == "d"
        assert names_by_branch["c"]["callees"][0]["node"].name == "d"

    def test_trace_cycle_marked(self, store) -> None:
        """Ciclo A->B->A deve ser marcado com cycle=True, não omitido."""
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="b", target_id="a", kind="calls"),
        ])

        result = trace_call_path(store, "a", direction="outgoing", max_depth=5)
        callees = result["callees"]
        assert len(callees) == 1
        assert callees[0]["node"].name == "b"
        # B chama A (ciclo de volta para a raiz)
        deeper = callees[0]["callees"]
        assert len(deeper) == 1
        assert deeper[0]["node"].name == "a"
        assert deeper[0].get("cycle") is True


class TestTraceCallSiteResolution:
    """Testes para resolução de call sites (Fix A + Fix B)."""

    def test_trace_prefers_definition_over_call_site(self, store) -> None:
        """Quando existem nó 'call' e nó 'function' com mesmo nome, trace
        deve selecionar a definição, não o call site.
        """
        store.upsert_nodes([
            Node(id="func_def", name="foo", kind="function",
                 file_path="def.py", language="python", line_start=10),
            Node(id="call_site", name="foo", kind="call",
                 file_path="caller.py", language="python", line_start=5),
        ])
        result = trace_call_path(store, "foo")
        assert result["symbol"] is not None
        assert result["symbol"].kind == "function"
        assert result["symbol"].id == "func_def"

    def test_trace_incoming_via_call_sites(self, store) -> None:
        """Call graph incoming de uma definição deve encontrar callers
        através de call sites com mesmo nome (Bug 2 do relatório).
        """
        store.upsert_nodes([
            Node(id="defn", name="bar", kind="function",
                 file_path="lib.py", language="python", line_start=20),
            Node(id="call1", name="bar", kind="call",
                 file_path="a.py", language="python", line_start=5),
            Node(id="call2", name="bar", kind="call",
                 file_path="b.py", language="python", line_start=10),
            Node(id="caller_a", name="func_a", kind="function",
                 file_path="a.py", language="python", line_start=1),
            Node(id="caller_b", name="func_b", kind="function",
                 file_path="b.py", language="python", line_start=1),
        ])
        # Parser cria caller → call_site, não caller → definição.
        store.upsert_edges([
            Edge(source_id="caller_a", target_id="call1", kind="calls"),
            Edge(source_id="caller_b", target_id="call2", kind="calls"),
        ])

        result = trace_call_path(store, "bar", direction="incoming")
        assert result["symbol"] is not None
        assert result["symbol"].id == "defn"
        caller_names = {c["node"].name for c in result["callers"]}
        assert caller_names == {"func_a", "func_b"}

    def test_trace_outgoing_resolves_call_site_to_definition(self, store) -> None:
        """Call graph outgoing de uma função deve resolver call sites para
        as definições correspondentes (Bug 2 do relatório)."""
        store.upsert_nodes([
            Node(id="caller_fn", name="do_work", kind="function",
                 file_path="caller.py", language="python", line_start=1),
            Node(id="callee_def", name="helper", kind="function",
                 file_path="lib.py", language="python", line_start=50),
            Node(id="call_x", name="helper", kind="call",
                 file_path="caller.py", language="python", line_start=5),
        ])
        # Parser: caller → call_site (não caller → definição)
        store.upsert_edges([
            Edge(source_id="caller_fn", target_id="call_x", kind="calls"),
        ])

        result = trace_call_path(store, "do_work", direction="outgoing")
        assert result["symbol"] is not None
        assert result["symbol"].id == "caller_fn"
        callees = result["callees"]
        assert len(callees) == 1
        # Deve resolver para a definição, não para o call site
        assert callees[0]["node"].id == "callee_def"
        assert callees[0]["node"].kind == "function"

    def test_trace_outgoing_keeps_call_site_when_no_definition(self, store) -> None:
        """Se não houver definição correspondente, mantém o call site."""
        store.upsert_nodes([
            Node(id="caller_fn", name="outer", kind="function",
                 file_path="a.py", language="python", line_start=1),
            Node(id="call_x", name="external_lib_func", kind="call",
                 file_path="a.py", language="python", line_start=3),
        ])
        store.upsert_edges([
            Edge(source_id="caller_fn", target_id="call_x", kind="calls"),
        ])

        result = trace_call_path(store, "outer", direction="outgoing")
        callees = result["callees"]
        assert len(callees) == 1
        # Sem definição — mantém call site
        assert callees[0]["node"].name == "external_lib_func"

    def test_trace_incoming_dedup_direct_and_via_call_site(self, store) -> None:
        """Se uma aresta direta caller→defn e um caminho caller→call_site→defn
        apontam para o mesmo caller, não deve duplicar."""
        store.upsert_nodes([
            Node(id="defn", name="baz", kind="function",
                 file_path="lib.py", language="python", line_start=10),
            Node(id="call_site", name="baz", kind="call",
                 file_path="a.py", language="python", line_start=5),
            Node(id="caller", name="uses", kind="function",
                 file_path="a.py", language="python", line_start=1),
        ])
        store.upsert_edges([
            # Caminho direto (modelo antigo)
            Edge(source_id="caller", target_id="defn", kind="calls"),
            # Caminho via call site (modelo parser)
            Edge(source_id="caller", target_id="call_site", kind="calls"),
        ])

        result = trace_call_path(store, "baz", direction="incoming")
        assert result["symbol"] is not None
        # Deve aparecer apenas uma vez (dedup por caller.id)
        assert len(result["callers"]) == 1
        assert result["callers"][0]["node"].name == "uses"

    def test_trace_fallback_to_call_site_when_no_definition(self, store) -> None:
        """Se só existem call sites (sem definição), trace ainda funciona
        e cai no fallback de _resolve_symbol (cobre linha 27)."""
        store.upsert_nodes([
            Node(id="call_x", name="external_fn", kind="call",
                 file_path="a.py", language="python", line_start=5),
        ])
        result = trace_call_path(store, "external_fn")
        assert result["symbol"] is not None
        assert result["symbol"].kind == "call"

    def test_trace_outgoing_cycle_via_call_site(self, store) -> None:
        """Ciclo envolvendo call site deve ser marcado, não omitido."""
        store.upsert_nodes([
            Node(id="defn_a", name="func_a", kind="function",
                 file_path="a.py", language="python", line_start=1),
            Node(id="defn_b", name="func_b", kind="function",
                 file_path="b.py", language="python", line_start=10),
            Node(id="call_b", name="func_b", kind="call",
                 file_path="a.py", language="python", line_start=3),
            Node(id="call_a", name="func_a", kind="call",
                 file_path="b.py", language="python", line_start=12),
        ])
        # func_a chama func_b via call site, func_b chama func_a via call site
        store.upsert_edges([
            Edge(source_id="defn_a", target_id="call_b", kind="calls"),
            Edge(source_id="defn_b", target_id="call_a", kind="calls"),
        ])

        result = trace_call_path(store, "func_a", direction="outgoing", max_depth=5)
        callees = result["callees"]
        assert len(callees) == 1
        # Resolvido para a definição
        assert callees[0]["node"].id == "defn_b"
        # func_b chama func_a (ciclo)
        deeper = callees[0]["callees"]
        assert len(deeper) == 1
        assert deeper[0]["node"].id == "defn_a"
        assert deeper[0].get("cycle") is True
