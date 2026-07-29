"""Testes para queries/diff.py — diff de símbolos contra um ref git."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from eizo.queries.diff import diff_against_ref


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Repositório git com um commit base contendo lib.py."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "lib.py").write_text("def helper():\n    pass\n\ndef old_func():\n    pass\n")
    _git(tmp_path, "add", "lib.py")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "branch", "base_ref")
    return tmp_path


class TestDiffAgainstRef:
    """Testa diff_against_ref() contra repositórios git reais."""

    def test_modified_file_shows_added_and_removed_symbols(self, git_repo: Path) -> None:
        (git_repo / "lib.py").write_text("def helper():\n    return 42\n\ndef new_func():\n    pass\n")

        result = diff_against_ref(git_repo, "base_ref")

        assert result["ref"] == "base_ref"
        assert len(result["files"]) == 1
        entry = result["files"][0]
        assert entry["file"] == "lib.py"
        assert entry["status"] == "modified"
        assert entry["added"] == [["new_func", "function"]]
        assert entry["removed"] == [["old_func", "function"]]

    def test_new_file_marked_as_added(self, git_repo: Path) -> None:
        (git_repo / "extra.py").write_text("def extra_thing():\n    pass\n")
        _git(git_repo, "add", "extra.py")

        result = diff_against_ref(git_repo, "base_ref")

        entry = next(f for f in result["files"] if f["file"] == "extra.py")
        assert entry["status"] == "added"
        assert entry["added"] == [["extra_thing", "function"]]
        assert entry["removed"] == []

    def test_deleted_file_marked_as_removed(self, git_repo: Path) -> None:
        (git_repo / "lib.py").unlink()

        result = diff_against_ref(git_repo, "base_ref")

        entry = next(f for f in result["files"] if f["file"] == "lib.py")
        assert entry["status"] == "removed"
        assert {tuple(s) for s in entry["removed"]} == {("helper", "function"), ("old_func", "function")}

    def test_no_symbol_changes_omits_file(self, git_repo: Path) -> None:
        """Mudança que não altera nenhuma definição (ex: só corpo de função)
        não aparece — o diff é sobre a superfície de símbolos."""
        (git_repo / "lib.py").write_text("def helper():\n    return 999  # corpo mudou\n\ndef old_func():\n    pass\n")

        result = diff_against_ref(git_repo, "base_ref")

        assert result["files"] == []

    def test_no_changes_returns_empty(self, git_repo: Path) -> None:
        result = diff_against_ref(git_repo, "base_ref")
        assert result["files"] == []

    def test_nonexistent_ref_raises(self, git_repo: Path) -> None:
        with pytest.raises(RuntimeError, match="unknown revision|bad revision|ambiguous"):
            diff_against_ref(git_repo, "ref_que_nao_existe")

    def test_non_git_directory_raises(self, tmp_path: Path) -> None:
        non_git = tmp_path / "plain"
        non_git.mkdir()
        (non_git / "a.py").write_text("x = 1\n")
        with pytest.raises(RuntimeError):
            diff_against_ref(non_git, "main")

    def test_non_parseable_extension_ignored(self, git_repo: Path) -> None:
        (git_repo / "README.md").write_text("# mudou\n")
        _git(git_repo, "add", "README.md")

        result = diff_against_ref(git_repo, "base_ref")

        assert all(f["file"] != "README.md" for f in result["files"])
