"""Testes para graph/store.py."""

from __future__ import annotations

from eizo.graph.models import Edge, Node
from eizo.graph.store import _extract_import_module_and_symbol, _module_hint_matches_file


class TestExtractImportModuleAndSymbol:
    """Testa _extract_import_module_and_symbol()."""

    def test_from_import_splits_module_and_symbol(self) -> None:
        assert _extract_import_module_and_symbol("config.get_config") == ("config", "get_config")

    def test_plain_import_has_no_symbol(self) -> None:
        """Import sem símbolo específico (Python 'import X', ou imports
        TS/JS que só capturam o caminho do módulo) não tem '.' — não há
        símbolo para extrair."""
        assert _extract_import_module_and_symbol("os") == ("os", None)


class TestModuleHintMatchesFile:
    """Testa _module_hint_matches_file()."""

    def test_matches_dotted_package_tail(self) -> None:
        assert _module_hint_matches_file("pkg.base", "/repo/pkg/base.py") is True

    def test_matches_relative_path_tail(self) -> None:
        """Path relativo estilo TS ('./components/Base')."""
        assert _module_hint_matches_file("./components/Base", "/repo/src/Base.tsx") is True

    def test_no_match_different_stem(self) -> None:
        assert _module_hint_matches_file("other", "/repo/base.py") is False


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

    def test_resolve_call_to_definition_finds_definition(self, store) -> None:
        """resolve_call_to_definition acha a definição com mesmo nome."""
        store.upsert_nodes([
            Node(id="defn", name="helper", kind="function", file_path="lib.py", language="python"),
            Node(id="call_site", name="helper", kind="call", file_path="app.py", language="python"),
        ])
        call_node = store.get_node("call_site")
        resolved = store.resolve_call_to_definition(call_node)
        assert resolved.id == "defn"
        assert resolved.kind == "function"

    def test_resolve_call_to_definition_falls_back_to_call_site(self, store) -> None:
        """Sem definição correspondente, retorna o próprio call site."""
        store.upsert_node(
            Node(id="call_site", name="external_func", kind="call", file_path="app.py", language="python")
        )
        call_node = store.get_node("call_site")
        resolved = store.resolve_call_to_definition(call_node)
        assert resolved.id == "call_site"

    def test_get_real_references_direct_edges(self, store) -> None:
        """get_real_references resolve arestas diretas calls/imports/inherits."""
        store.upsert_nodes([
            Node(id="target", name="target", kind="function", file_path="t.py", language="python"),
            Node(id="caller", name="caller", kind="function", file_path="c.py", language="python"),
            Node(id="importer", name="importer", kind="function", file_path="i.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="caller", target_id="target", kind="calls"),
            Edge(source_id="importer", target_id="target", kind="imports"),
        ])

        refs = store.get_real_references("target", "target")
        by_id = {n.id: kind for n, kind in refs}
        assert by_id == {"caller": "calls", "importer": "imports"}

    def test_get_real_references_resolves_call_sites(self, store) -> None:
        """get_real_references resolve caller → call_site → definição (mesmo nome)."""
        store.upsert_nodes([
            Node(id="defn", name="helper", kind="function", file_path="lib.py", language="python"),
            Node(id="call_site", name="helper", kind="call", file_path="app.py", language="python"),
            Node(id="caller", name="caller", kind="function", file_path="app.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="caller", target_id="call_site", kind="calls"),
        ])

        refs = store.get_real_references("defn", "helper")
        assert refs == [(store.get_node("caller"), "calls")]

    def test_get_real_references_dedupes_direct_and_call_site(self, store) -> None:
        """Mesmo caller via aresta direta e via call site não deve duplicar."""
        store.upsert_nodes([
            Node(id="defn", name="helper", kind="function", file_path="lib.py", language="python"),
            Node(id="call_site", name="helper", kind="call", file_path="app.py", language="python"),
            Node(id="caller", name="caller", kind="function", file_path="app.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="caller", target_id="defn", kind="calls"),
            Edge(source_id="caller", target_id="call_site", kind="calls"),
        ])

        refs = store.get_real_references("defn", "helper")
        assert len(refs) == 1
        assert refs[0][0].id == "caller"

    def test_get_real_references_resolves_inherits_stub(self, store) -> None:
        """Uma classe base referenciada só via herança tem um stub externo
        criado no arquivo da subclasse (metadata.external=True) — a aresta
        'inherits' aponta para esse stub, não para a definição real.
        get_real_references precisa resolver o stub de volta."""
        store.upsert_nodes([
            Node(id="real_base", name="Base", kind="class", file_path="base.py", language="python"),
            Node(
                id="base_stub", name="Base", kind="class", file_path="child.py",
                language="python", metadata={"external": True},
            ),
            Node(id="child", name="Child", kind="class", file_path="child.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="child", target_id="base_stub", kind="inherits"),
        ])

        refs = store.get_real_references("real_base", "Base")
        assert refs == [(store.get_node("child"), "inherits")]

    def test_get_real_references_resolves_import_stub(self, store) -> None:
        """Um import 'from module import symbol' cria um nó kind='import'
        com nome 'module.symbol' — get_real_references precisa extrair o
        símbolo e confirmar via module_hint antes de creditar o
        referrer."""
        store.upsert_nodes([
            Node(id="real_fn", name="get_config", kind="function", file_path="config.py", language="python"),
            Node(
                id="import_stub", name="config.get_config", kind="import",
                file_path="user.py", language="python",
            ),
            Node(id="user_file", name="user.py", kind="file", file_path="user.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="user_file", target_id="import_stub", kind="imports"),
        ])

        refs = store.get_real_references("real_fn", "get_config")
        assert refs == [(store.get_node("user_file"), "imports")]

    def test_get_real_references_disambiguates_by_file_and_import(self, store) -> None:
        """Duas definições homônimas em arquivos diferentes: um call site
        só deve ser creditado à que é realmente importada no arquivo do
        caller (via resolve_call_to_definition), não às duas."""
        store.upsert_nodes([
            Node(id="defn_a", name="connect", kind="function", file_path="mod_a.py", language="python"),
            Node(id="defn_b", name="connect", kind="function", file_path="mod_b.py", language="python"),
            Node(
                id="import_stub", name="mod_a.connect", kind="import",
                file_path="caller.py", language="python",
            ),
            Node(id="call_site", name="connect", kind="call", file_path="caller.py", language="python"),
            Node(id="caller", name="do_it", kind="function", file_path="caller.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="caller", target_id="import_stub", kind="imports"),
            Edge(source_id="caller", target_id="call_site", kind="calls"),
        ])

        refs_a = store.get_real_references("defn_a", "connect")
        refs_b = store.get_real_references("defn_b", "connect")

        # defn_a (mod_a) é a que caller.py importa — deve receber o crédito
        # das duas referências (import + call).
        assert {kind for _, kind in refs_a} == {"imports", "calls"}
        # defn_b (mod_b) não é importada por caller.py — nenhuma referência.
        assert refs_b == []

    def test_get_real_references_unknown_node_returns_empty(self, store) -> None:
        """Node id inexistente retorna lista vazia, não lança erro."""
        assert store.get_real_references("does-not-exist", "whatever") == []

    def test_get_real_references_skips_inherits_stub_for_different_definition(
        self, store
    ) -> None:
        """Um stub externo 'Base' que na verdade resolve para uma OUTRA
        definição 'Base' (arquivo diferente) não deve creditar sua
        subclasse à definição errada."""
        store.upsert_nodes([
            Node(id="base_x", name="Base", kind="class", file_path="x/base.py", language="python"),
            Node(id="base_y", name="Base", kind="class", file_path="y/base.py", language="python"),
            Node(
                id="stub_in_child", name="Base", kind="class", file_path="child.py",
                language="python", metadata={"external": True},
            ),
            Node(id="child", name="Child", kind="class", file_path="child.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="child", target_id="stub_in_child", kind="inherits"),
        ])

        # Sem sinal de import para desambiguar, cai no desempate
        # determinístico (ordenado por file_path) — "x/base.py" vence.
        refs_x = store.get_real_references("base_x", "Base")
        refs_y = store.get_real_references("base_y", "Base")
        assert refs_x == [(store.get_node("child"), "inherits")]
        assert refs_y == []

    def test_disambiguate_prefers_unique_same_file_among_many(self, store) -> None:
        """Com 3+ candidatos homônimos, prefere o único que está no mesmo
        arquivo de quem referencia."""
        store.upsert_nodes([
            Node(id="a1", name="run", kind="function", file_path="a.py", language="python"),
            Node(id="b1", name="run", kind="function", file_path="b.py", language="python"),
            Node(id="c1", name="run", kind="function", file_path="c.py", language="python"),
        ])
        candidates = [store.get_node("a1"), store.get_node("b1"), store.get_node("c1")]
        resolved = store._disambiguate_definitions("b.py", candidates)
        assert resolved is not None
        assert resolved.id == "b1"

    def test_disambiguate_falls_back_deterministically_when_still_ambiguous(
        self, store
    ) -> None:
        """Sem sinal de mesmo-arquivo nem de import, o desempate final é
        determinístico (ordenado por file_path, line_start) — não depende
        da ordem arbitrária de retorno do SQLite."""
        store.upsert_nodes([
            Node(id="z1", name="run", kind="function", file_path="z.py", language="python", line_start=1),
            Node(id="a1", name="run", kind="function", file_path="a.py", language="python", line_start=1),
        ])
        candidates = [store.get_node("z1"), store.get_node("a1")]
        resolved = store._disambiguate_definitions("unrelated.py", candidates)
        assert resolved is not None
        assert resolved.id == "a1"  # "a.py" < "z.py"

    def test_clear_all(self, store) -> None:
        """Limpa todo o grafo."""
        store.upsert_node(Node(id="a1", name="foo", kind="function", file_path="a.py", language="python"))
        store.upsert_edge(Edge(source_id="a1", target_id="a1", kind="calls"))

        store.clear_all()
        stats = store.get_stats()
        assert stats.total_nodes == 0
        assert stats.total_edges == 0
