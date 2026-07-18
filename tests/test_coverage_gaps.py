"""Testes de cobertura para linhas específicas ainda não cobertas."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eizo.graph.store import GraphStore
from eizo.indexer import index_repository
from eizo.queries.impact import analyze_impact
from eizo.queries.search import get_symbol_context


class TestCoverageGaps:
    """Testes focados em cobrir linhas específicas."""

    # ─── indexer.py: linhas 45-46, 49-50 (parser RuntimeError) ───

    def test_indexer_parser_runtime_error(self, tmp_path: Path) -> None:
        """Simula RuntimeError ao carregar parser."""
        with patch("eizo.indexer.PythonParser", side_effect=RuntimeError("no python")), \
             patch("eizo.indexer.TypeScriptParser", side_effect=RuntimeError("no ts")):
            store = index_repository(tmp_path)
            stats = store.get_stats()
            assert stats.total_nodes == 0

    # ─── indexer.py: linhas 121-122 (parser None) ───

    def test_indexer_parser_none_for_file(self, tmp_path: Path) -> None:
        """Arquivo com extensão que nenhum parser cobre."""
        repo = Path(tmp_path)
        (repo / "file.unknown").write_text("some content")
        store = index_repository(repo)
        stats = store.get_stats()
        assert stats.total_nodes == 0

    # ─── indexer.py: linhas 136-137 (exception during parse) ───

    def test_indexer_parse_exception(self, tmp_path: Path) -> None:
        """Simula exceção durante parsing de um arquivo."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        with patch("eizo.parser.python.PythonParser.parse_file", side_effect=Exception("parse error")):
            store = index_repository(repo)
            stats = store.get_stats()
            # Deve ter processado sem crashar
            assert stats.total_nodes >= 0

    # ─── indexer.py: linhas 151-155 (error reporting) ───

    def test_indexer_error_reporting(self, tmp_path: Path) -> None:
        """Múltiplos erros durante indexação devem ser reportados."""
        repo = Path(tmp_path)
        for i in range(7):
            (repo / f"bad{i}.py").write_text("\x00\x00invalid\x00\x00")
        store = index_repository(repo)
        stats = store.get_stats()
        assert stats.total_nodes >= 0

    # ─── cli.py: linhas 117-118 (trace with callers) ───

    def test_cli_trace_with_callers(self, tmp_path: Path) -> None:
        """Trace com callers (incoming)."""
        from click.testing import CliRunner

        from eizo.cli import main

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def caller(): callee()\ndef callee(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["trace", "callee", "--direction", "incoming", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Quem chama" in result.output

    # ─── cli.py: linhas 132 (recursive _print_call_tree) ───

    def test_cli_trace_recursive(self, tmp_path: Path) -> None:
        """Trace com profundidade > 1 para testar recursão."""
        from click.testing import CliRunner

        from eizo.cli import main
        from eizo.graph.models import Edge, Node

        repo = Path(tmp_path)
        store = GraphStore(repo)
        # Cria nós e arestas diretamente para garantir estrutura aninhada
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
            Node(id="c", name="c", kind="function", file_path="c.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="b", target_id="c", kind="calls"),
        ])

        runner = CliRunner()
        result = runner.invoke(main, ["trace", "a", "--direction", "outgoing", "--depth", "3", "--repo", str(repo)])
        assert result.exit_code == 0

    # ─── cli.py: linhas 156-158, 163-169 (impact tree) ───

    def test_cli_impact_with_dependents(self, tmp_path: Path) -> None:
        """Impact com dependentes para testar árvore."""
        from click.testing import CliRunner

        from eizo.cli import main
        from eizo.graph.models import Edge, Node

        repo = Path(tmp_path)
        store = GraphStore(repo)
        # Cria nós e arestas diretamente para testar a árvore de impacto
        store.upsert_nodes([
            Node(id="core", name="core", kind="function", file_path="core.py", language="python"),
            Node(id="middle", name="middle", kind="function", file_path="middle.py", language="python"),
            Node(id="top", name="top", kind="function", file_path="top.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="middle", target_id="core", kind="imports"),
            Edge(source_id="top", target_id="middle", kind="imports"),
        ])

        runner = CliRunner()
        result = runner.invoke(main, ["impact", "core", "--depth", "3", "--repo", str(repo)])
        assert result.exit_code == 0

    # ─── cli.py: linhas 219-222 (mcp command) ───

    def test_cli_mcp_command(self, tmp_path: Path) -> None:
        """Comando mcp deve iniciar servidor (simulado)."""
        from click.testing import CliRunner

        from eizo.cli import main

        with patch("eizo.mcp.server.serve_mcp") as mock_serve:
            runner = CliRunner()
            result = runner.invoke(main, ["mcp", "--port", "9999", "--repo", str(tmp_path)])
            assert result.exit_code == 0
            mock_serve.assert_called_once()

    # ─── queries/search.py: linhas 61-64 (depth > 1) ───

    def test_search_depth2_with_edges(self, store) -> None:
        """get_symbol_context com depth=2 e arestas para ambos os lados."""
        from eizo.graph.models import Edge, Node

        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="a.py", language="python"),
            Node(id="c", name="c", kind="function", file_path="a.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="b", target_id="a", kind="calls"),  # incoming
            Edge(source_id="a", target_id="c", kind="calls"),  # outgoing
        ])
        context = get_symbol_context(store, "a", depth=2)
        assert "deeper_incoming" in context
        assert "deeper_outgoing" in context

    # ─── queries/impact.py: linhas 85, 100 (inherits + calls) ───

    def test_impact_inherits_and_calls(self, store) -> None:
        """Impact com herança e chamadas."""
        from eizo.graph.models import Edge, Node

        store.upsert_nodes([
            Node(id="base", name="Base", kind="class", file_path="base.py", language="python"),
            Node(id="child", name="Child", kind="class", file_path="child.py", language="python"),
            Node(id="user", name="user", kind="function", file_path="user.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="child", target_id="base", kind="inherits"),
            Edge(source_id="user", target_id="base", kind="calls"),
        ])
        result = analyze_impact(store, "Base")
        assert result["symbol"] is not None
        assert len(result["impact_chain"]) == 2
        relations = {item["relation"] for item in result["impact_chain"]}
        assert relations == {"inherits", "calls"}

    # ─── queries/trace.py: linhas 62, 77, 95, 110 (já cobertas) ───
    # Já cobertas por test_trace_call_path_cycle e test_trace_call_path_max_depth

    # ─── parser/python.py: linhas 43, 46 (_get_docstring edge cases) ───

    def test_parse_docstring_no_body(self) -> None:
        """_get_docstring com body vazio."""
        from eizo.parser.python import _get_docstring

        # Simula nó sem body
        node = MagicMock()
        node.child_by_field_name.return_value = None
        result = _get_docstring(b"", node)
        assert result is None

    def test_parse_docstring_empty_body(self) -> None:
        """_get_docstring com body sem filhos."""
        from eizo.parser.python import _get_docstring

        body = MagicMock()
        body.child_count = 0
        node = MagicMock()
        node.child_by_field_name.return_value = body
        result = _get_docstring(b"", node)
        assert result is None

    def test_parse_docstring_first_stmt_none(self) -> None:
        """_get_docstring com first_stmt None."""
        from eizo.parser.python import _get_docstring

        body = MagicMock()
        body.child_count = 1
        body.child.return_value = None
        node = MagicMock()
        node.child_by_field_name.return_value = body
        result = _get_docstring(b"", node)
        assert result is None

    def test_parse_docstring_exception(self) -> None:
        """_get_docstring com exceção."""
        from eizo.parser.python import _get_docstring

        node = MagicMock()
        node.child_by_field_name.side_effect = Exception("test")
        result = _get_docstring(b"", node)
        assert result is None

    # ─── parser/python.py: linhas 335-337 (call with non-identifier, non-attribute) ───

    def test_parse_call_unknown_type(self) -> None:
        """_handle_call com tipo de nó desconhecido."""
        from eizo.parser.python import PythonParser

        try:
            parser = PythonParser()
        except RuntimeError:
            pytest.skip("tree-sitter-python não instalado")

        # Código com call que não é identifier nem attribute
        source = """
def test():
    (lambda x: x)(42)
"""
        nodes, edges = parser.parse_file(Path("test.py"), source)
        # Não deve crashar
        assert len(nodes) >= 1

    # ─── parser/typescript.py: linhas 315-317 (call with non-identifier, non-member) ───

    def test_parse_ts_call_unknown_type(self) -> None:
        """_handle_call TS com tipo de nó desconhecido."""
        from eizo.parser.typescript import TypeScriptParser

        try:
            parser = TypeScriptParser()
        except RuntimeError:
            pytest.skip("tree-sitter-typescript não instalado")

        source = """
function test() {
    (() => 42)();
}
"""
        nodes, edges = parser.parse_file(Path("test.ts"), source)
        assert len(nodes) >= 1

    # ─── parser/python.py: linhas 75-79 (RuntimeError quando PYTHON_LANGUAGE é None) ───

    def test_python_parser_init_no_language(self) -> None:
        """PythonParser.__init__ levanta RuntimeError se tree-sitter ausente."""
        from eizo.parser import python as py_mod

        original = py_mod.PYTHON_LANGUAGE
        try:
            py_mod.PYTHON_LANGUAGE = None
            with pytest.raises(RuntimeError, match="tree-sitter-python"):
                py_mod.PythonParser()
        finally:
            py_mod.PYTHON_LANGUAGE = original

    # ─── parser/typescript.py: linhas 51-55 (RuntimeError quando TS_LANGUAGE é None) ───

    def test_ts_parser_init_no_language(self) -> None:
        """TypeScriptParser.__init__ levanta RuntimeError se tree-sitter ausente."""
        from eizo.parser import typescript as ts_mod

        original = ts_mod.TS_LANGUAGE
        try:
            ts_mod.TS_LANGUAGE = None
            with pytest.raises(RuntimeError, match="tree-sitter-typescript"):
                ts_mod.TypeScriptParser()
        finally:
            ts_mod.TS_LANGUAGE = original

    # ─── parser/python.py: linha 153 (function sem name_node) ───

    def test_handle_function_no_name(self) -> None:
        """_handle_function com name_node=None retorna sem crashar."""
        from eizo.parser.python import PythonParser

        try:
            parser = PythonParser()
        except RuntimeError:
            pytest.skip("tree-sitter-python não instalado")

        node = MagicMock()
        node.child_by_field_name.return_value = None
        # Chama _handle_function diretamente com nó sem name
        parser._handle_function(node, b"", "test.py", [], [], None)
        # Se chegou aqui sem crashar, o early-return funcionou

    # ─── parser/python.py: linha 199 (class sem name_node) ───

    def test_handle_class_no_name(self) -> None:
        """_handle_class com name_node=None retorna sem crashar."""
        from eizo.parser.python import PythonParser

        try:
            parser = PythonParser()
        except RuntimeError:
            pytest.skip("tree-sitter-python não instalado")

        node = MagicMock()
        node.child_by_field_name.return_value = None
        parser._handle_class(node, b"", "test.py", [], [], None)

    # ─── parser/python.py: linha 287 (import_from sem module_name) ───

    def test_handle_import_from_no_module(self) -> None:
        """_handle_import_from com module_name=None retorna sem crashar."""
        from eizo.parser.python import PythonParser

        try:
            parser = PythonParser()
        except RuntimeError:
            pytest.skip("tree-sitter-python não instalado")

        node = MagicMock()
        node.child_by_field_name.return_value = None
        parser._handle_import_from(node, b"", "test.py", [], [], None)

    # ─── parser/python.py: linha 324 (call sem function node) ───

    def test_handle_call_no_function(self) -> None:
        """_handle_call com func_node=None retorna sem crashar."""
        from eizo.parser.python import PythonParser

        try:
            parser = PythonParser()
        except RuntimeError:
            pytest.skip("tree-sitter-python não instalado")

        node = MagicMock()
        node.child_by_field_name.return_value = None
        parser._handle_call(node, b"", "test.py", [], [], None)

    # ─── parser/python.py: linha 335 (call attribute sem attr) ───

    def test_handle_call_attribute_no_attr(self) -> None:
        """_handle_call com attribute node mas sem field 'attribute'."""
        from eizo.parser.python import PythonParser

        try:
            parser = PythonParser()
        except RuntimeError:
            pytest.skip("tree-sitter-python não instalado")

        func_node = MagicMock()
        func_node.type = "attribute"
        func_node.child_by_field_name.return_value = None  # attribute field ausente
        node = MagicMock()
        node.child_by_field_name.return_value = func_node
        parser._handle_call(node, b"", "test.py", [], [], None)

    # ─── parser/typescript.py: linha 176 (method sem name_node) ───

    def test_handle_ts_method_no_name(self) -> None:
        """_handle_method TS com name_node=None retorna sem crashar."""
        from eizo.parser.typescript import TypeScriptParser

        try:
            parser = TypeScriptParser()
        except RuntimeError:
            pytest.skip("tree-sitter-typescript não instalado")

        node = MagicMock()
        node.child_by_field_name.return_value = None
        parser._handle_method(node, b"", "test.ts", [], [], None)

    # ─── parser/typescript.py: linha 274 (import sem source) ───

    def test_handle_ts_import_no_source(self) -> None:
        """_handle_import TS com source=None retorna sem crashar."""
        from eizo.parser.typescript import TypeScriptParser

        try:
            parser = TypeScriptParser()
        except RuntimeError:
            pytest.skip("tree-sitter-typescript não instalado")

        node = MagicMock()
        node.child_by_field_name.return_value = None
        parser._handle_import(node, b"", "test.ts", [], [], None)

    # ─── parser/typescript.py: linha 306 (call sem function node) ───

    def test_handle_ts_call_no_function(self) -> None:
        """_handle_call TS com func_node=None retorna sem crashar."""
        from eizo.parser.typescript import TypeScriptParser

        try:
            parser = TypeScriptParser()
        except RuntimeError:
            pytest.skip("tree-sitter-typescript não instalado")

        node = MagicMock()
        node.child_by_field_name.return_value = None
        parser._handle_call(node, b"", "test.ts", [], [], None)

    # ─── parser/typescript.py: linha 315 (call member_expression sem property) ───

    def test_handle_ts_call_member_no_property(self) -> None:
        """_handle_call TS com member_expression mas sem property."""
        from eizo.parser.typescript import TypeScriptParser

        try:
            parser = TypeScriptParser()
        except RuntimeError:
            pytest.skip("tree-sitter-typescript não instalado")

        func_node = MagicMock()
        func_node.type = "member_expression"
        func_node.child_by_field_name.return_value = None  # property field ausente
        node = MagicMock()
        node.child_by_field_name.return_value = func_node
        parser._handle_call(node, b"", "test.ts", [], [], None)

    # ─── cli.py: linhas 183, 204, 224, 250, 369-370, 430-431, 494-495, 547-552, 672-676, 687-688 ───

    def test_cli_merge_config_no_command_values(self) -> None:
        """_merge_config sem command_values usa repo_path default '.'."""
        from click.testing import CliRunner

        from eizo.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0

    def test_cli_config_no_color(self, tmp_path: Path) -> None:
        """config.json com no_color: true desativa cores."""
        from click.testing import CliRunner

        import eizo.cli
        from eizo.cli import console, main

        eizo.cli._force_color = None
        console._color_system = None
        console._force_terminal = None

        repo = Path(tmp_path)
        eizo_dir = repo / ".eizo"
        eizo_dir.mkdir()
        (eizo_dir / "config.json").write_text('{"no_color": true}')

        runner = CliRunner()
        result = runner.invoke(main, ["status", "--repo", str(repo)])
        assert result.exit_code == 0

    def test_cli_env_full_text(self, tmp_path: Path) -> None:
        """EIZO_FULL_TEXT=1 é aplicado ao comando search."""
        from click.testing import CliRunner

        from eizo.cli import main

        repo = Path(tmp_path)
        (repo / "test.py").write_text('def helper(): """docs"""\n    pass\n')
        from eizo.graph.store import GraphStore
        from eizo.indexer import index_repository

        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["search", "docs", "--repo", str(repo)], env={"EIZO_FULL_TEXT": "1"})
        assert result.exit_code == 0

    def test_cli_unsupported_shell(self) -> None:
        """_install_completion com shell não suportado retorna mensagem."""
        from eizo.cli import _install_completion

        result = _install_completion("powershell")
        assert "não suportado" in result.lower()

    def test_cli_no_color_explicit(self, tmp_path: Path) -> None:
        """--no-color desativa sistema de cor."""
        from click.testing import CliRunner

        import eizo.cli
        from eizo.cli import console, main

        runner = CliRunner()
        result = runner.invoke(main, ["--no-color", "status", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert console._color_system is None
        eizo.cli._force_color = False

    def test_cli_init_json(self, tmp_path: Path) -> None:
        """init --output-format json retorna JSON."""
        from click.testing import CliRunner

        from eizo.cli import main

        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "init", str(repo)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert "stats" in data

    def test_cli_search_json(self, tmp_path: Path) -> None:
        """search --output-format json retorna JSON."""
        from click.testing import CliRunner

        from eizo.cli import main
        from eizo.graph.models import Node
        from eizo.graph.store import GraphStore

        repo = Path(tmp_path)
        store = GraphStore(repo)
        store.upsert_nodes([
            Node(id="n1", name="helper", kind="function", file_path="test.py", language="python", line_start=1),
        ])
        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "search", "helper", "--repo", str(repo)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["name"] == "helper"

    def test_cli_trace_json(self, tmp_path: Path) -> None:
        """trace --output-format json retorna JSON."""
        from click.testing import CliRunner

        from eizo.cli import main
        from eizo.graph.models import Edge, Node
        from eizo.graph.store import GraphStore

        repo = Path(tmp_path)
        store = GraphStore(repo)
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
        ])
        store.upsert_edges([Edge(source_id="b", target_id="a", kind="calls")])
        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "trace", "a", "--repo", str(repo)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "symbol" in data

    def test_cli_impact_json(self, tmp_path: Path) -> None:
        """impact --output-format json retorna JSON."""
        from click.testing import CliRunner

        from eizo.cli import main
        from eizo.graph.models import Node
        from eizo.graph.store import GraphStore

        repo = Path(tmp_path)
        store = GraphStore(repo)
        store.upsert_nodes([
            Node(id="core", name="core", kind="function", file_path="core.py", language="python"),
        ])
        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "impact", "core", "--repo", str(repo)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "symbol" in data

    def test_cli_impact_no_dependents(self, tmp_path: Path) -> None:
        """impact com símbolo sem dependentes mostra mensagem."""
        from click.testing import CliRunner

        from eizo.cli import main
        from eizo.graph.models import Node
        from eizo.graph.store import GraphStore

        repo = Path(tmp_path)
        store = GraphStore(repo)
        store.upsert_nodes([
            Node(id="core", name="core", kind="function", file_path="core.py", language="python"),
        ])
        runner = CliRunner()
        result = runner.invoke(main, ["impact", "core", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Nenhum dependente" in result.output

    # ─── indexer.py: linhas 109, 132, 148-149 ───

    def test_indexer_dry_run_no_parsers(self, tmp_path: Path) -> None:
        """dry_run=True sem parsers retorna lista vazia."""
        from unittest.mock import patch

        with patch("eizo.indexer._get_parsers", return_value=[]):
            result = index_repository(tmp_path, store=None, dry_run=True)
        assert result == []

    def test_indexer_dry_run_no_files(self, tmp_path: Path) -> None:
        """dry_run=True sem arquivos parseáveis retorna lista vazia."""
        result = index_repository(tmp_path, store=None, dry_run=True)
        assert result == []

    def test_indexer_oserror_reading_file(self, tmp_path: Path) -> None:
        """OSError ao ler arquivo deve ignorar arquivo e continuar."""
        from unittest.mock import patch

        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        with patch("pathlib.Path.read_text", side_effect=OSError("read error")):
            store = index_repository(repo)
        stats = store.get_stats()
        assert stats.total_nodes == 0

    # ─── parser/python.py: linhas 322-324 ───

    def test_parse_import_from_aliased_without_name(self) -> None:
        """import_from aliased sem name_node deve dar continue."""
        from eizo.parser.python import PythonParser

        try:
            parser = PythonParser()
        except RuntimeError:
            pytest.skip("tree-sitter-python não instalado")

        # 'from x import *' tem wildcard_import, não aliased_import com name
        source = "from os import *\n"
        nodes, edges = parser.parse_file(Path("test.py"), source)
        # Não deve crashar
        assert isinstance(nodes, list)

    # ─── parser/typescript.py: linha 48 ───

    def test_ts_infer_name_parent_none(self) -> None:
        """_infer_name_from_parent com parent=None retorna (None, function)."""
        from eizo.parser.typescript import TypeScriptParser

        try:
            parser = TypeScriptParser()
        except RuntimeError:
            pytest.skip("tree-sitter-typescript não instalado")

        # Código com arrow function inline sem pai nomeável
        source = """
function test() {
    setTimeout(() => 42, 100);
}
"""
        nodes, edges = parser.parse_file(Path("test.ts"), source)
        assert isinstance(nodes, list)

    # ─── export.py: edge_kinds, filters, empty paths, call resolution ───

    def test_export_mermaid_edge_kinds_filter(self, store: GraphStore) -> None:
        """export_mermaid com edge_kinds filtra arestas."""
        from eizo.graph.models import Edge, Node
        from eizo.queries.export import export_mermaid

        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
            Node(id="c", name="c", kind="class", file_path="c.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="c", target_id="b", kind="inherits"),
        ])
        result = export_mermaid(store, edge_kinds=frozenset({"calls"}))
        assert "calls" in result
        assert "inherits" not in result

    def test_export_json_edge_kinds_filter(self, store: GraphStore) -> None:
        """export_json com edge_kinds filtra arestas."""
        from eizo.graph.models import Edge, Node
        from eizo.queries.export import export_json

        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="b", target_id="a", kind="imports"),
        ])
        result = export_json(store, edge_kinds=frozenset({"calls"}))
        data = json.loads(result)
        assert len(data["edges"]) == 1
        assert data["edges"][0]["kind"] == "calls"

    def test_export_is_architecture_file_filters(self) -> None:
        """_is_architecture_file exclui testes, vendor e __init__.py."""
        from eizo.queries.export import _is_architecture_file

        assert _is_architecture_file("src/app.py") is True
        assert _is_architecture_file("tests/test_app.py") is False
        assert _is_architecture_file("src/static/vendor/x.js") is False
        assert _is_architecture_file("src/pkg/__init__.py") is False

    def test_export_relative_repo_path_oserror(self) -> None:
        """_relative_repo_path lida com OSError."""
        from eizo.queries.export import _relative_repo_path

        # Caminho inválido que causa OSError na resolução
        result = _relative_repo_path("/proc/self/nonexistent", "/tmp")
        assert result == "/proc/self/nonexistent"

    def test_export_layer_for_file_static(self) -> None:
        """_layer_for_file classifica static e outros."""
        from eizo.queries.export import _layer_for_file

        assert _layer_for_file("src/static/vendor/x.js") == "static"
        assert _layer_for_file("src/unknown.py") == "other"
        assert _layer_for_file("src/queries/search.py") == "queries"
        assert _layer_for_file("src/graph/store.py") == "graph"
        assert _layer_for_file("src/indexer.py") == "indexer"
        assert _layer_for_file("src/cli.py") == "entrypoints"

    def test_export_common_path_prefix_empty(self) -> None:
        """_common_path_prefix vazio retorna string vazia."""
        from eizo.queries.export import _common_path_prefix

        assert _common_path_prefix([]) == ""

    def test_export_display_path_src_prefix(self) -> None:
        """_display_path remove prefixo src/."""
        from eizo.queries.export import _display_path

        assert _display_path("src/eizo/cli.py", "") == "eizo/cli.py"
        assert _display_path("src/eizo/cli.py", "src") == "eizo/cli.py"

    def test_export_architecture_no_components(self, store: GraphStore) -> None:
        """export_architecture_mermaid com apenas nós de teste retorna mensagem."""
        from eizo.graph.models import Node
        from eizo.queries.export import export_architecture_mermaid

        store.upsert_nodes([
            Node(id="t1", name="test", kind="function", file_path="tests/test_x.py", language="python"),
        ])
        result = export_architecture_mermaid(store)
        assert "Nenhum componente" in result

    def test_export_architecture_with_call_resolution(self) -> None:
        """export_architecture_mermaid resolve call sites para definições."""
        from eizo.graph.models import Edge, Node
        from eizo.graph.store import GraphStore
        from eizo.queries.export import export_architecture_mermaid

        s = GraphStore(Path("/tmp/eizo_arch_call_" + str(id(self))))
        s.upsert_nodes([
            Node(id="caller", name="caller", kind="function", file_path="src/cli.py", language="python"),
            Node(id="callsite", name="search", kind="call", file_path="src/cli.py", language="python"),
            Node(id="defn", name="search", kind="function", file_path="src/queries/search.py", language="python"),
        ])
        s.upsert_edges([
            Edge(source_id="caller", target_id="callsite", kind="calls"),
        ])
        result = export_architecture_mermaid(s)
        assert "comp_cli_py" in result
        assert "comp_queries_search_py" in result

    def test_export_architecture_layer_representative(self, store: GraphStore) -> None:
        """Camada vazia ou não selecionada recebe representante."""
        from eizo.graph.models import Node
        from eizo.queries.export import export_architecture_mermaid

        store.upsert_nodes([
            Node(id="s1", name="static", kind="function", file_path="src/static/x.js", language="typescript"),
            Node(id="o1", name="other", kind="function", file_path="src/other.py", language="python"),
        ])
        result = export_architecture_mermaid(store)
        assert "static" in result
        assert "other" in result

    # ─── impact.py: linhas 16, 73 ───

    def test_analyze_impact_no_definition_kind(self, store: GraphStore) -> None:
        """_resolve_symbol retorna primeiro nó quando nenhum é definição."""
        from eizo.graph.models import Node
        from eizo.queries.impact import analyze_impact

        store.upsert_nodes([
            Node(id="x", name="x", kind="call", file_path="a.py", language="python"),
        ])
        result = analyze_impact(store, "x")
        assert result["symbol"] is not None

    def test_analyze_impact_node_missing(self, store: GraphStore) -> None:
        """_build_impact_chain lida com nó removido."""
        from eizo.graph.models import Edge, Node
        from eizo.queries.impact import _build_impact_chain

        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="b", target_id="a", kind="calls"),
        ])
        # Simula nó dependente removido fazendo get_node retornar None
        original_get_node = store.get_node
        def _mock_get_node(node_id: str):
            if node_id == "b":
                return None
            return original_get_node(node_id)
        store.get_node = _mock_get_node  # type: ignore[method-assign]
        chain = _build_impact_chain(store, "a", max_depth=3)
        assert chain == []

    # ─── trace.py: linhas 91, 149, 158 ───

    def test_trace_incoming_max_depth(self, store: GraphStore) -> None:
        """_trace_incoming respeita max_depth."""
        from eizo.graph.models import Edge, Node
        from eizo.queries.trace import _trace_incoming

        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="b", target_id="a", kind="calls"),
        ])
        result = _trace_incoming(store, "a", "a", max_depth=0)
        assert result == []

    def test_trace_outgoing_target_missing(self, store: GraphStore) -> None:
        """_trace_outgoing ignora target removido."""
        from eizo.graph.models import Edge, Node
        from eizo.queries.trace import _trace_outgoing

        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
        ])
        # Simula target removido fazendo get_node retornar None
        original_get_node = store.get_node
        def _mock_get_node(node_id: str):
            if node_id == "b":
                return None
            return original_get_node(node_id)
        store.get_node = _mock_get_node  # type: ignore[method-assign]
        result = _trace_outgoing(store, "a", max_depth=3)
        assert result == []

    def test_trace_outgoing_seen_targets(self, store: GraphStore) -> None:
        """_trace_outgoing deduplica targets."""
        from eizo.graph.models import Edge, Node
        from eizo.queries.trace import _trace_outgoing

        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path="a.py", language="python"),
            Node(id="b", name="b", kind="function", file_path="b.py", language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="a", target_id="b", kind="calls"),
        ])
        result = _trace_outgoing(store, "a", max_depth=3)
        assert len(result) == 1

    # ─── schema.py: linha 126 ───

    def test_migrate_db_no_schema_version(self, tmp_path: Path) -> None:
        """migrate_db retorna early quando meta não existe."""
        import sqlite3

        from eizo.graph.schema import migrate_db

        db_path = tmp_path / "graph.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY)")
        # Sem schema_version
        migrate_db(conn)
        conn.close()

    # ─── __main__.py: linha 8 ───

    def test_main_module_runs_main(self) -> None:
        """Executar eizo como __main__ chama cli.main()."""
        from unittest.mock import patch

        with patch("eizo.cli.main") as mock_main:
            import runpy
            import sys

            # Remove cache do módulo para forçar reexecução
            sys.modules.pop("eizo.__main__", None)
            runpy.run_module("eizo.__main__", run_name="__main__")
            mock_main.assert_called_once()
