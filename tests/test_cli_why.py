"""Testes para o comando 'eizo why' (CLI)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from eizo.cli import main
from eizo.indexer import index_repository


class TestCliWhy:
    """Testa o comando 'eizo why'."""

    def _chain_repo(self, repo: Path) -> None:
        (repo / "a.py").write_text(
            "def top():\n    middle()\n\ndef middle():\n    bottom()\n\ndef bottom():\n    pass\n\n"
            "def isolated():\n    pass\n"
        )
        index_repository(repo)

    def test_why_forward_direction(self, tmp_path: Path) -> None:
        self._chain_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["why", "top", "bottom", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "'top' depende de 'bottom'" in result.output
        assert "top → middle → bottom" in result.output

    def test_why_backward_direction_is_labeled(self, tmp_path: Path) -> None:
        """why(bottom, top) só existe na direção contrária — sinalizado na saída."""
        self._chain_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["why", "bottom", "top", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "'top' depende de 'bottom'" in result.output
        assert "invertida" in result.output

    def test_why_no_path(self, tmp_path: Path) -> None:
        self._chain_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["why", "top", "isolated", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "Nenhum caminho" in result.output

    def test_why_unknown_symbol(self, tmp_path: Path) -> None:
        self._chain_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["why", "top", "nao_existe", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "não encontrado" in result.output

    def test_why_json_format(self, tmp_path: Path) -> None:
        self._chain_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "why", "top", "bottom", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["found"] is True
        assert parsed["direction"] == "forward"
        assert [n["name"] for n in parsed["path"]] == ["top", "middle", "bottom"]

    def test_why_max_depth_option(self, tmp_path: Path) -> None:
        self._chain_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["why", "top", "bottom", "--max-depth", "1", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "Nenhum caminho" in result.output

    def test_why_unindexed_repo_fails(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["why", "a", "b", "--repo", str(tmp_path)])
        assert result.exit_code == 1
        assert "não indexado" in result.output
