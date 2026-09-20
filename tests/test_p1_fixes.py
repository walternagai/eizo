"""Testes de regressão para os P1s da revisão repo-full-review.

Cada classe trava o contrato corrigido de um P1:

- TestWheelPackages: find_packages inclui eizo.parser e eizo.mcp (o wheel
  real precisa dos parsers e do servidor MCP — antes, install não-editável
  quebrava `eizo mcp` com ModuleNotFoundError).
- TestStoreTransactionRollback: writers multi-statement do GraphStore fazem
  rollback em exceção (transação não fica aberta nem persiste lote parcial).
- TestIndexerRelativeIgnore: _should_ignore só testa partes RELATIVAS à raiz.
- TestParserDeepNesting: parsers Python/TS resistem a aninhamento profundo
  de input válido (parse parcial, nunca exceção).
- TestFindHotspotsContract: find_hotspots retorna list[Node] conforme
  docs/api.md (contrato estável da API pública).
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from setuptools import find_packages

from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore
from eizo.parser.base import MAX_AST_DEPTH
from eizo.parser.csharp import CSharpParser
from eizo.parser.go import GoParser
from eizo.parser.java import JavaParser
from eizo.parser.php import PhpParser
from eizo.parser.python import PythonParser
from eizo.parser.ruby import RubyParser
from eizo.parser.rust import RustParser
from eizo.parser.typescript import TypeScriptParser
from eizo.queries.analysis import find_hotspots


class TestWheelPackages:
    """O wheel precisa conter TODOS os subpacotes com código."""

    def test_find_packages_includes_parser_and_mcp(self) -> None:
        """find_packages (config do pyproject) inclui parser e mcp."""
        pkgs = find_packages(where="src", include=["eizo*"])
        assert "eizo.parser" in pkgs
        assert "eizo.mcp" in pkgs
        assert "eizo.graph" in pkgs
        assert "eizo.queries" in pkgs

    def test_parser_and_mcp_importable(self) -> None:
        """Os pacotes são importáveis (não apenas nomes no wheel)."""
        import eizo.mcp  # noqa: F401
        import eizo.parser  # noqa: F401


class _FlakyConnection:
    """Wrapper de sqlite3.Connection que injeta falha em uma statement."""

    def __init__(self, real: sqlite3.Connection, fail_on: int) -> None:
        self._real = real
        self._fail_on = fail_on
        self._calls = 0

    def _maybe_fail(self) -> None:
        self._calls += 1
        if self._calls == self._fail_on:
            raise sqlite3.OperationalError("database is locked")

    def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
        self._maybe_fail()
        return self._real.execute(sql, *args)  # type: ignore[arg-type]

    def executemany(self, sql: str, *args: object) -> None:
        self._maybe_fail()
        self._real.executemany(sql, *args)  # type: ignore[arg-type]

    def commit(self) -> None:
        self._real.commit()

    def rollback(self) -> None:
        self._real.rollback()


class TestStoreTransactionRollback:
    """Writers multi-statement são atômicos: exceção → rollback."""

    def test_upsert_nodes_rollback_on_failure(self, tmp_path: Path) -> None:
        """Falha na sincronização FTS não persiste o lote parcial de nodes."""
        store = GraphStore(tmp_path)
        node = Node(
            id="a" * 16, name="func_a", kind="function", file_path="a.py",
            language="python", line_start=1, line_end=1,
        )
        # Falha na 2a statement (DELETE FTS) — nodes já foram inseridos.
        store._conn = _FlakyConnection(store.conn, fail_on=2)  # noqa: SLF001
        with contextlib.suppress(sqlite3.OperationalError):
            store.upsert_nodes([node])

        # Rollback: nada persistiu
        assert store.get_node(node.id) is None
        # Transação não ficou aberta: próximo writer funciona normalmente
        store.upsert_nodes([node])
        assert store.get_node(node.id) is not None

    def test_delete_nodes_by_file_rollback_on_failure(self, tmp_path: Path) -> None:
        """Falha no meio do purge não apaga pela metade."""
        store = GraphStore(tmp_path)
        node = Node(
            id="b" * 16, name="func_b", kind="function", file_path="b.py",
            language="python", line_start=1, line_end=1,
        )
        store.upsert_nodes([node])

        # Falha na 2a statement do purge (edges target) — nada persiste.
        store._conn = _FlakyConnection(store.conn, fail_on=2)  # noqa: SLF001
        with contextlib.suppress(sqlite3.OperationalError):
            store.delete_nodes_by_file("b.py")

        assert store.get_node(node.id) is not None  # rollback preservou o nó
        store._conn = None  # volta à conexão real
        store.delete_nodes_by_file("b.py")
        assert store.get_node(node.id) is None  # próximo writer funciona


class TestIndexerRelativeIgnore:
    """_should_ignore só compara partes relativas à raiz do repo."""

    def test_index_repo_under_ignored_ancestor(self, tmp_path: Path) -> None:
        """Repo dentro de .../build/ indexa normalmente (integração)."""
        from eizo.indexer import index_repository

        root = tmp_path / "build" / "projeto"
        root.mkdir(parents=True)
        (root / "mod.py").write_text("def alvo(): pass\n")

        store = index_repository(root)
        assert store.get_nodes_by_name("alvo", kind="function")


class TestParserDeepNesting:
    """Aninhamento profundo de input válido não estoura a pilha."""

    def test_python_deep_nested_calls(self) -> None:
        """f(f(...)) com ~500 níveis: parse parcial, sem exceção."""
        depth = 500
        source = "def top():\n    return " + "f(" * depth + "x" + ")" * depth
        nodes, edges = PythonParser().parse_file(Path("deep.py"), source)
        assert any(n.name == "top" for n in nodes)

    def test_typescript_deep_nested_calls(self) -> None:
        """g(g(...)) com ~500 níveis: parse parcial, sem exceção."""
        depth = 500
        source = "function top() { return " + "g(" * depth + "x" + ")" * depth + "; }"
        nodes, edges = TypeScriptParser().parse_file(Path("deep.ts"), source)
        assert any(n.name == "top" for n in nodes)

    def test_malformed_still_never_raises(self) -> None:
        """Contrato do fuzz suite segue de pé com o guard no lugar."""
        parser = PythonParser()
        nodes, edges = parser.parse_file(Path("bad.py"), "def broken(:\n")
        assert isinstance(nodes, list) and isinstance(edges, list)

    @pytest.mark.parametrize(
        "parser_cls, filename, build_source",
        [
            ("go", "deep.go", lambda d: "package main\n\nfunc top() {\n\t_ = " + "f(" * d + "x" + ")" * d + "\n}"),
            ("rust", "deep.rs", lambda d: "fn top() { " + "f(" * d + "x" + ")" * d + "; }"),
            ("java", "deep.java", lambda d: "class T { void top() { " + "f(" * d + "x" + ")" * d + "; } }"),
            ("csharp", "deep.cs", lambda d: "class t { void top() { " + "F(" * d + "x" + ")" * d + "; } }"),
            ("php", "deep.php", lambda d: "<?php\nfunction top() { " + "f(" * d + "x" + ")" * d + "; }"),
            ("ruby", "deep.rb", lambda d: "def top\n  " + "f(" * d + "x" + ")" * d + "\nend"),
        ],
    )
    def test_deep_nesting_never_raises(
        self,
        parser_cls: str,
        filename: str,
        build_source: Any,
    ) -> None:
        """~2x MAX_AST_DEPTH de nesting: parse parcial, sem exceção (6 parsers)."""
        parser_cls_map = {
            "go": GoParser,
            "rust": RustParser,
            "java": JavaParser,
            "csharp": CSharpParser,
            "php": PhpParser,
            "ruby": RubyParser,
        }
        depth = MAX_AST_DEPTH * 2
        source = build_source(depth)
        parser = parser_cls_map[parser_cls]()
        nodes, edges = parser.parse_file(Path(filename), source)
        assert any(n.name == "top" for n in nodes)


class TestFindHotspotsContract:
    """find_hotspots retorna list[Node] (contrato docs/api.md)."""

    def _make_store(self, tmp_path: Path) -> GraphStore:
        store = GraphStore(tmp_path)
        store.upsert_nodes([
            Node(id="h" * 16, name="func_h", kind="function", file_path="m.py",
                 language="python", line_start=1, line_end=1),
            Node(id="c1" * 8, name="caller1", kind="function", file_path="m.py",
                 language="python", line_start=2, line_end=2),
            Node(id="c2" * 8, name="caller2", kind="function", file_path="m.py",
                 language="python", line_start=3, line_end=3),
        ])
        store.upsert_edges([
            Edge(source_id="c1" * 8, target_id="h" * 16, kind="calls"),
            Edge(source_id="c2" * 8, target_id="h" * 16, kind="calls"),
        ])
        return store

    def test_returns_nodes_with_metadata(self, tmp_path: Path) -> None:
        """Retorno é list[Node] com metadata['reference_count']."""
        results = find_hotspots(self._make_store(tmp_path), min_references=1)
        assert results
        first = results[0]
        assert isinstance(first, Node)
        assert first.name == "func_h"
        assert first.metadata["reference_count"] == 2

    def test_cli_hotspots_json_contract(self, tmp_path: Path) -> None:
        """CLI hotspots --output-format json: shape {node, reference_count}."""
        from click.testing import CliRunner

        from eizo.cli import main
        from eizo.indexer import index_repository

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "mod.py").write_text(
            "def used():\n    return 1\n\n"
            "def caller_a():\n    return used()\n\n"
            "def caller_b():\n    return used()\n"
        )
        index_repository(repo, force=True)

        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "hotspots", "--repo", str(repo), "--min-refs", "1"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed[0]["node"]["name"] == "used"
        assert parsed[0]["reference_count"] == 2
