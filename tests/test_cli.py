"""Testes para CLI (Click commands via CliRunner)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from eizo.cli import main
from eizo.graph.store import GraphStore
from eizo.indexer import index_repository


class TestCliInit:
    """Testes para o comando 'eizo init'."""

    def test_init_no_args(self, tmp_path: Path) -> None:
        """Init sem argumentos deve usar diretório atual."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            # Cria um arquivo .py para indexar
            repo = Path(td)
            (repo / "test.py").write_text("x = 1\n")
            result = runner.invoke(main, ["init", str(repo)])
            assert result.exit_code == 0
            assert "Indexando" in result.output

    def test_init_invalid_path(self) -> None:
        """Init com caminho inválido deve mostrar erro."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "/caminho/inexistente"])
        assert result.exit_code != 0

    def test_init_rebuild(self, tmp_path: Path) -> None:
        """Init --rebuild deve limpar e reindexar."""
        runner = CliRunner()
        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        result = runner.invoke(main, ["init", "--rebuild", str(repo)])
        assert result.exit_code == 0


class TestCliSearch:
    """Testes para o comando 'eizo search'."""

    def test_search_no_results(self, tmp_path: Path) -> None:
        """Search sem resultados deve mostrar mensagem."""
        runner = CliRunner()
        result = runner.invoke(main, ["search", "nonexistent", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Nenhum resultado" in result.output

    def test_search_with_results(self, tmp_path: Path) -> None:
        """Search com resultados deve mostrar tabela."""
        # Indexa um repositório primeiro
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def hello(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["search", "hello", "--path", str(repo)])
        assert result.exit_code == 0
        assert "hello" in result.output

    def test_search_with_filters(self, tmp_path: Path) -> None:
        """Search com filtros de tipo e linguagem."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "foo", "--kind", "function",
            "--language", "python", "--path", str(repo),
        ])
        assert result.exit_code == 0
        assert "foo" in result.output


class TestCliTrace:
    """Testes para o comando 'eizo trace'."""

    def test_trace_not_found(self, tmp_path: Path) -> None:
        """Trace de símbolo inexistente."""
        runner = CliRunner()
        result = runner.invoke(main, ["trace", "nonexistent", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "não encontrado" in result.output

    def test_trace_found(self, tmp_path: Path) -> None:
        """Trace de símbolo existente."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def caller(): callee()\ndef callee(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["trace", "caller", "--path", str(repo)])
        assert result.exit_code == 0
        assert "Call graph" in result.output


class TestCliImpact:
    """Testes para o comando 'eizo impact'."""

    def test_impact_not_found(self, tmp_path: Path) -> None:
        """Impact de símbolo inexistente."""
        runner = CliRunner()
        result = runner.invoke(main, ["impact", "nonexistent", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "não encontrado" in result.output

    def test_impact_found(self, tmp_path: Path) -> None:
        """Impact de símbolo existente."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def helper(): pass\ndef user(): helper()\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["impact", "helper", "--path", str(repo)])
        assert result.exit_code == 0
        assert "Análise de impacto" in result.output


class TestCliArch:
    """Testes para o comando 'eizo arch'."""

    def test_arch_empty(self, tmp_path: Path) -> None:
        """Arch em repositório vazio."""
        runner = CliRunner()
        result = runner.invoke(main, ["arch", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Grafo vazio" in result.output

    def test_arch_with_data(self, tmp_path: Path) -> None:
        """Arch com dados."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["arch", "--path", str(repo)])
        assert result.exit_code == 0
        assert "Visão Arquitetural" in result.output


class TestCliStatus:
    """Testes para o comando 'eizo status'."""

    def test_status_empty(self, tmp_path: Path) -> None:
        """Status em repositório vazio."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Grafo vazio" in result.output

    def test_status_with_data(self, tmp_path: Path) -> None:
        """Status com dados."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["status", "--path", str(repo)])
        assert result.exit_code == 0
        assert "Status do Grafo" in result.output


class TestCliVersion:
    """Testes para --version."""

    def test_version(self) -> None:
        """--version deve mostrar a versão."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
