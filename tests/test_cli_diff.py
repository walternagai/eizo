"""Testes para o comando 'eizo diff' (CLI)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from eizo.cli import main


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "lib.py").write_text("def helper():\n    pass\n\ndef old_func():\n    pass\n")
    _git(tmp_path, "add", "lib.py")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "branch", "base_ref")
    return tmp_path


class TestCliDiff:
    """Testa o comando 'eizo diff'. Não depende de `eizo init` — diff não usa o grafo."""

    def test_diff_shows_added_and_removed_symbols(self, git_repo: Path) -> None:
        (git_repo / "lib.py").write_text("def helper():\n    return 1\n\ndef new_func():\n    pass\n")

        runner = CliRunner()
        result = runner.invoke(main, ["diff", "base_ref", "--repo", str(git_repo)])

        assert result.exit_code == 0
        assert "modified" in result.output
        assert "+ function new_func" in result.output
        assert "- function old_func" in result.output

    def test_diff_no_changes(self, git_repo: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["diff", "base_ref", "--repo", str(git_repo)])
        assert result.exit_code == 0
        assert "Nenhuma mudança" in result.output

    def test_diff_json_format(self, git_repo: Path) -> None:
        (git_repo / "lib.py").write_text("def helper():\n    return 1\n\ndef new_func():\n    pass\n")

        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "diff", "base_ref", "--repo", str(git_repo)])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ref"] == "base_ref"
        assert parsed["files"][0]["added"] == [["new_func", "function"]]

    def test_diff_nonexistent_ref_fails(self, git_repo: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["diff", "ref_que_nao_existe", "--repo", str(git_repo)])
        assert result.exit_code == 1
        assert "revision" in result.output or "revisão" in result.output or "unknown" in result.output

    def test_diff_does_not_require_init(self, git_repo: Path) -> None:
        """diff funciona sem `.eizo/graph.db` — não depende do grafo indexado."""
        assert not (git_repo / ".eizo").exists()
        runner = CliRunner()
        result = runner.invoke(main, ["diff", "base_ref", "--repo", str(git_repo)])
        assert result.exit_code == 0
        assert not (git_repo / ".eizo").exists()
