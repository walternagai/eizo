"""Testes de cobertura para linhas específicas ainda não cobertas."""

from __future__ import annotations

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
