"""Testes para queries de análise: dead code detection e hotspots.

Cobre:
- queries/analysis.py: find_dead_code(), find_hotspots()
- CLI: eizo dead, eizo hotspots
- MCP: find_dead_code_symbols, get_hotspots
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from eizo.cli import main
from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore
from eizo.mcp.server import create_server, serve_mcp
from eizo.queries.analysis import find_dead_code, find_hotspots


def _get_tool_fn(mcp: object, name: str) -> object:
    """Extrai a função original de uma tool registrada no FastMCP."""
    tool = mcp._tool_manager._tools[name]  # type: ignore[attr-defined]
    return tool.fn


# ─── Fixtures ──────────────────────────────────────────────────


def _make_node(
    nid: str,
    name: str,
    kind: str = "function",
    file_path: str = "test.py",
    language: str = "python",
    line_start: int = 1,
) -> Node:
    """Cria um Node com defaults convenientes."""
    return Node(
        id=nid, name=name, kind=kind, file_path=file_path,
        language=language, line_start=line_start, line_end=line_start + 5,
    )


@pytest.fixture
def analysis_store(store: GraphStore) -> GraphStore:
    """Store com grafo estruturado para testar dead code e hotspots.

    Estrutura:
        main → helper_a → utility  (utility é hotspot: 3 refs)
        main → helper_b → utility
        dead_func  (sem callers → dead code)
        orphan_class  (sem callers → dead code)
    """
    store.upsert_nodes([
        _make_node("main", "main", "function"),
        _make_node("helper_a", "helper_a", "function", "a.py", line_start=10),
        _make_node("helper_b", "helper_b", "function", "b.py", line_start=20),
        _make_node("utility", "utility", "function", "c.py", line_start=30),
        _make_node("dead_func", "dead_func", "function", "d.py", line_start=40),
        _make_node("orphan_class", "orphan_class", "class", "e.py", line_start=50),
    ])
    store.upsert_edges([
        Edge(source_id="main", target_id="helper_a", kind="calls"),
        Edge(source_id="main", target_id="helper_b", kind="calls"),
        Edge(source_id="helper_a", target_id="utility", kind="calls"),
        Edge(source_id="helper_b", target_id="utility", kind="calls"),
        # utility tem 2 callers (hotspot)
    ])
    return store


# ─── find_dead_code (query) ────────────────────────────────────


class TestFindDeadCode:
    """Testa find_dead_code()."""

    def test_finds_dead_symbols(self, analysis_store: GraphStore) -> None:
        """Dead code: dead_func e orphan_class não têm callers."""
        results = find_dead_code(analysis_store)
        names = {n.name for n in results}
        assert "dead_func" in names
        assert "orphan_class" in names

    def test_excludes_referenced_symbols(self, analysis_store: GraphStore) -> None:
        """Símbolos com callers não aparecem como dead code."""
        results = find_dead_code(analysis_store)
        names = {n.name for n in results}
        assert "utility" not in names  # tem 2 callers
        assert "helper_a" not in names  # tem 1 caller (main)
        assert "helper_b" not in names

    def test_excludes_default_entrypoints(self, analysis_store: GraphStore) -> None:
        """main é entrypoint padrão — não aparece como dead code mesmo sem callers."""
        results = find_dead_code(analysis_store)
        names = {n.name for n in results}
        assert "main" not in names

    def test_custom_entrypoints(self, analysis_store: GraphStore) -> None:
        """Entrypoints customizados excluem símbolos específicos."""
        # Marca dead_func como entrypoint — não deve aparecer
        results = find_dead_code(analysis_store, entrypoints=frozenset({"dead_func"}))
        names = {n.name for n in results}
        assert "dead_func" not in names
        assert "orphan_class" in names  # ainda aparece

    def test_empty_store(self, store: GraphStore) -> None:
        """Store vazio retorna lista vazia."""
        results = find_dead_code(store)
        assert results == []

    def test_limit_parameter(self, analysis_store: GraphStore) -> None:
        """Limit restringe número de resultados."""
        results = find_dead_code(analysis_store, limit=1)
        assert len(results) == 1

    def test_excludes_external_stubs(self, store: GraphStore) -> None:
        """Nós stub externos (metadata.external=True) não são dead code."""
        from eizo.graph.models import Node as ModelNode

        store.upsert_nodes([
            ModelNode(id="ext", name="ExternalBase", kind="class", file_path="a.py",
                      language="python", metadata={"external": True}),
            ModelNode(id="real_dead", name="really_dead", kind="function", file_path="b.py",
                      language="python"),
        ])
        results = find_dead_code(store)
        names = {n.name for n in results}
        assert "really_dead" in names
        assert "ExternalBase" not in names


# ─── find_hotspots (query) ─────────────────────────────────────


class TestFindHotspots:
    """Testa find_hotspots()."""

    def test_returns_most_referenced(self, analysis_store: GraphStore) -> None:
        """Utility (2 refs) é o hotspot principal."""
        results = find_hotspots(analysis_store)
        assert len(results) >= 1
        # Utility deve estar no topo (2 refs)
        assert results[0]["node"].name == "utility"
        assert results[0]["reference_count"] == 2

    def test_min_references_filter(self, analysis_store: GraphStore) -> None:
        """min_references=3 exclui utility (tem só 2)."""
        results = find_hotspots(analysis_store, min_references=3)
        assert results == []

    def test_limit_parameter(self, analysis_store: GraphStore) -> None:
        """Limit restringe resultados."""
        results = find_hotspots(analysis_store, limit=1)
        assert len(results) == 1

    def test_empty_store(self, store: GraphStore) -> None:
        """Store vazio retorna lista vazia."""
        results = find_hotspots(store)
        assert results == []

    def test_ordering_by_reference_count(self, store: GraphStore) -> None:
        """Resultados ordenados por reference_count descendente."""
        store.upsert_nodes([
            _make_node("a", "func_a"),
            _make_node("b", "func_b"),
            _make_node("c", "func_c"),
            _make_node("caller1", "caller1"),
            _make_node("caller2", "caller2"),
            _make_node("caller3", "caller3"),
        ])
        store.upsert_edges([
            Edge(source_id="caller1", target_id="a", kind="calls"),
            Edge(source_id="caller2", target_id="a", kind="calls"),
            Edge(source_id="caller3", target_id="a", kind="calls"),
            Edge(source_id="caller1", target_id="b", kind="calls"),
        ])
        results = find_hotspots(store, min_references=1)
        # func_a (3 refs) deve vir antes de func_b (1 ref)
        assert results[0]["node"].name == "func_a"
        assert results[0]["reference_count"] == 3


# ─── Integração: parser + indexer reais (não fixtures idealizadas) ──
#
# analysis_store constrói arestas `caller → definição` diretamente, mas o
# parser real produz `caller → call_site` (nó kind='call') que precisa ser
# resolvido pelo nome. Estes testes indexam código Python real para garantir
# que find_dead_code/find_hotspots funcionam contra a forma de grafo que a
# produção realmente gera.


class TestFindDeadCodeRealIndexer:
    """Testa find_dead_code() contra grafo produzido pelo indexer real."""

    def test_unused_function_is_dead(self, tmp_path: Path) -> None:
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "mod.py").write_text(
            "def used():\n    return 1\n\n"
            "def unused():\n    return 2\n\n"
            "def caller():\n    return used()\n"
        )
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        names = {n.name for n in find_dead_code(store)}
        assert "unused" in names
        assert "used" not in names  # tem 1 caller real


class TestFindHotspotsRealIndexer:
    """Testa find_hotspots() contra grafo produzido pelo indexer real."""

    def test_reference_count_matches_real_callers(self, tmp_path: Path) -> None:
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "mod.py").write_text(
            "def used():\n    return 1\n\n"
            "def caller_a():\n    return used()\n\n"
            "def caller_b():\n    return used()\n"
        )
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        results = find_hotspots(store, min_references=1)
        by_name = {r["node"].name: r["reference_count"] for r in results}
        # 'used' tem exatamente 2 callers reais — não inflado por arestas
        # estruturais 'contains' (que ligariam cada função ao arquivo).
        assert by_name["used"] == 2


# ─── CLI: eizo dead ─────────────────────────────────────────────


class TestCliDead:
    """Testa o comando 'eizo dead'."""

    def test_dead_no_results(self, tmp_path: Path) -> None:
        """Dead em repositório vazio."""
        runner = CliRunner()
        result = runner.invoke(main, ["dead", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Nenhum código morto" in result.output

    def test_dead_with_results(self, tmp_path: Path) -> None:
        """Dead mostra código morto detectado, com JSON validando os nomes exatos."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text(
            "def used(): pass\n"
            "def caller(): used()\n"
            "def unused_func(): pass\n"
        )
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(
            main, ["--format", "json", "dead", "--path", str(repo)]
        )
        assert result.exit_code == 0
        names = {n["name"] for n in json.loads(result.output)}
        # caller e unused_func não têm ninguém que os chame.
        assert names == {"caller", "unused_func"}
        # used tem 1 caller (caller) — não deve ser dead code.
        assert "used" not in names

    def test_dead_json_format(self, tmp_path: Path) -> None:
        """Dead com --format json retorna JSON."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def unused(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(main, ["--format", "json", "dead", "--path", str(repo)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)

    def test_dead_custom_entrypoint(self, tmp_path: Path) -> None:
        """--entrypoint exclui símbolo específico."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def my_entry(): pass\ndef dead(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(
            main, ["dead", "--entrypoint", "my_entry", "--path", str(repo)]
        )
        assert result.exit_code == 0


# ─── CLI: eizo hotspots ────────────────────────────────────────


class TestCliHotspots:
    """Testa o comando 'eizo hotspots'."""

    def test_hotspots_empty(self, tmp_path: Path) -> None:
        """Hotspots em repositório vazio."""
        runner = CliRunner()
        result = runner.invoke(main, ["hotspots", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Nenhum hotspot" in result.output

    def test_hotspots_with_data(self, tmp_path: Path) -> None:
        """Hotspots mostra símbolos referenciados."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text(
            "def helper(): pass\n"
            "def a(): helper()\n"
            "def b(): helper()\n"
        )
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(main, ["hotspots", "--path", str(repo), "--min-refs", "1"])
        assert result.exit_code == 0
        assert "Hotspots" in result.output or "Nenhum hotspot" in result.output

    def test_hotspots_json_format(self, tmp_path: Path) -> None:
        """Hotspots com --format json retorna JSON."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text(
            "def helper(): pass\ndef a(): helper()\ndef b(): helper()\n"
        )
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(
            main, ["--format", "json", "hotspots", "--path", str(repo), "--min-refs", "1"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)


# ─── MCP: find_dead_code_symbols e get_hotspots ────────────────


class TestMcpAnalysisTools:
    """Testa as tools MCP de análise."""

    def test_find_dead_code_symbols(self, analysis_store: GraphStore) -> None:
        """find_dead_code_symbols retorna JSON com dead code."""
        mcp = create_server(analysis_store, port=12345)
        fn = _get_tool_fn(mcp, "find_dead_code_symbols")
        result = fn()
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        names = {n["name"] for n in parsed}
        assert "dead_func" in names
        assert "orphan_class" in names

    def test_find_dead_code_symbols_with_entrypoints(
        self, analysis_store: GraphStore
    ) -> None:
        """find_dead_code_symbols com entrypoints customizados."""
        mcp = create_server(analysis_store, port=12345)
        fn = _get_tool_fn(mcp, "find_dead_code_symbols")
        result = fn(entrypoints=["dead_func", "orphan_class"])
        parsed = json.loads(result)
        names = {n["name"] for n in parsed}
        assert "dead_func" not in names
        assert "orphan_class" not in names

    def test_get_hotspots(self, analysis_store: GraphStore) -> None:
        """get_hotspots retorna JSON com hotspots."""
        mcp = create_server(analysis_store, port=12345)
        fn = _get_tool_fn(mcp, "get_hotspots")
        result = fn(min_references=1)
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        assert parsed[0]["node"]["name"] == "utility"
        assert parsed[0]["reference_count"] == 2

    def test_get_hotspots_empty(self, store: GraphStore) -> None:
        """get_hotspots com store vazio retorna lista vazia."""
        mcp = create_server(store, port=12345)
        fn = _get_tool_fn(mcp, "get_hotspots")
        result = fn()
        parsed = json.loads(result)
        assert parsed == []


# ─── MCP: serve_mcp com transport stdio ────────────────────────


class TestServeMcpTransport:
    """Testa serve_mcp com diferentes transportes."""

    def test_serve_mcp_stdio(self, store: GraphStore) -> None:
        """serve_mcp com transport='stdio' chama mcp.run(transport='stdio')."""
        with patch("eizo.mcp.server.create_server") as mock_create:
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            serve_mcp(store, port=9999, transport="stdio")
            mock_create.assert_called_once_with(store, 9999)
            mock_mcp.run.assert_called_once_with(transport="stdio")

    def test_serve_mcp_sse_default(self, store: GraphStore) -> None:
        """serve_mcp sem transport usa 'sse' por padrão."""
        with patch("eizo.mcp.server.create_server") as mock_create:
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            serve_mcp(store, port=9999)
            mock_mcp.run.assert_called_once_with(transport="sse")
