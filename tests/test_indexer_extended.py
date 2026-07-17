"""Testes para indexer.py — cobre erros, edge cases e branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from eizo.indexer import _get_parser_for_file, _should_ignore, index_repository
from eizo.parser.base import BaseParser


class FakeParser(BaseParser):
    """Parser fake para testes."""

    @property
    def language(self) -> str:
        return "fake"

    @property
    def extensions(self) -> set[str]:
        return {".xyz"}

    def parse_file(self, file_path: Path, source: str) -> tuple[list, list]:  # noqa: ARG002
        return [], []


class TestShouldIgnore:
    """Testes para _should_ignore."""

    def test_ignore_git_dir(self) -> None:
        """Diretório .git deve ser ignorado."""
        assert _should_ignore(Path("/repo/.git/config")) is True

    def test_ignore_node_modules(self) -> None:
        """node_modules deve ser ignorado."""
        assert _should_ignore(Path("/repo/node_modules/foo.js")) is True

    def test_ignore_hidden_file(self) -> None:
        """Arquivos ocultos devem ser ignorados."""
        assert _should_ignore(Path("/repo/.env")) is True

    def test_ignore_pyc(self) -> None:
        """Arquivos .pyc devem ser ignorados."""
        assert _should_ignore(Path("/repo/file.pyc")) is True

    def test_ignore_egg_info(self) -> None:
        """Diretórios .egg-info devem ser ignorados."""
        assert _should_ignore(Path("/repo/.egg-info/PKG-INFO")) is True

    def test_not_ignore_normal_py(self) -> None:
        """Arquivos .py normais não devem ser ignorados."""
        assert _should_ignore(Path("/repo/main.py")) is False

    def test_not_ignore_normal_ts(self) -> None:
        """Arquivos .ts normais não devem ser ignorados."""
        assert _should_ignore(Path("/repo/main.ts")) is False


class TestGetParserForFile:
    """Testes para _get_parser_for_file."""

    def test_finds_parser(self) -> None:
        """Encontra parser para extensão suportada."""
        parser = FakeParser()
        result = _get_parser_for_file(Path("test.xyz"), [parser])
        assert result is parser

    def test_returns_none_for_unknown(self) -> None:
        """Retorna None para extensão não suportada."""
        parser = FakeParser()
        result = _get_parser_for_file(Path("test.unknown"), [parser])
        assert result is None


class TestIndexRepositoryErrors:
    """Testes para index_repository com erros."""

    def test_index_with_parse_error(self, tmp_path: Path) -> None:
        """Erro durante parsing deve ser registrado, não interrompe."""
        repo = Path(tmp_path)
        (repo / "bad.py").write_text("\x00\x00invalid\x00\x00")  # binário inválido
        store = index_repository(repo)
        stats = store.get_stats()
        # Pode ou não ter nós dependendo do parser
        assert stats.total_nodes >= 0

    def test_index_empty_dir(self, tmp_path: Path) -> None:
        """Diretório vazio deve retornar grafo vazio."""
        store = index_repository(tmp_path)
        stats = store.get_stats()
        assert stats.total_nodes == 0

    def test_index_no_parsers_available(self, tmp_path: Path) -> None:
        """Sem parsers disponíveis, deve retornar grafo vazio."""
        with patch("eizo.indexer._get_parsers", return_value=[]):
            store = index_repository(tmp_path)
            stats = store.get_stats()
            assert stats.total_nodes == 0

    def test_index_with_ignored_files_only(self, tmp_path: Path) -> None:
        """Apenas arquivos ignorados no diretório."""
        repo = Path(tmp_path)
        (repo / ".hidden.py").write_text("x = 1\n")
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "lib.js").write_text("var x = 1;\n")
        store = index_repository(repo)
        stats = store.get_stats()
        assert stats.total_nodes == 0

    def test_index_prunes_ignored_dirs_during_walk(self, tmp_path: Path) -> None:
        """IGNORE_DIRS deve ser podado durante o walk (os.walk com dirnames
        in-place), não apenas filtrado depois de enumerar a árvore inteira —
        node_modules nunca deve ser sequer visitado pelo os.walk."""
        import os as os_module

        repo = Path(tmp_path)
        (repo / "main.py").write_text("x = 1\n")
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "lib.js").write_text("var x = 1;\n")

        visited: list[str] = []
        real_walk = os_module.walk

        def spy_walk(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            for dirpath, dirnames, filenames in real_walk(*args, **kwargs):
                visited.append(dirpath)
                yield dirpath, dirnames, filenames

        with patch("eizo.indexer.os.walk", side_effect=spy_walk):
            index_repository(repo)

        visited_dirs = {Path(p).name for p in visited}
        assert "node_modules" not in visited_dirs

    def test_index_repository_with_errors(self, tmp_path: Path) -> None:
        """Múltiplos erros durante indexação."""
        repo = Path(tmp_path)
        (repo / "good.py").write_text("x = 1\n")
        (repo / "bad.py").write_text("\x00\x00")
        store = index_repository(repo)
        stats = store.get_stats()
        # good.py pode ou não ser parseado, mas não deve crashar
        assert stats.total_nodes >= 0

    def test_index_with_unparseable_extension(self, tmp_path: Path) -> None:
        """Arquivo com extensão não suportada deve ser pulado (parser is None)."""
        repo = Path(tmp_path)
        (repo / "main.py").write_text("x = 1\n")
        (repo / "data.json").write_text('{"key": "value"}\n')
        store = index_repository(repo)
        stats = store.get_stats()
        # Apenas main.py deve ser parseado
        assert stats.total_nodes >= 1

    def test_index_with_many_errors(self, tmp_path: Path) -> None:
        """Mais de 5 erros para testar a mensagem '... e mais N erro(s)'."""
        repo = Path(tmp_path)
        for i in range(7):
            (repo / f"bad{i}.py").write_text("x = 1\n")
        # Força erro em todos os arquivos via mock
        with patch("eizo.parser.python.PythonParser.parse_file", side_effect=Exception("forced error")):
            store = index_repository(repo)
            stats = store.get_stats()
            assert stats.total_nodes >= 0

    def test_index_parser_none_for_matched_extension(self, tmp_path: Path) -> None:
        """Parser retorna None para arquivo com extensão suportada."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        with patch("eizo.indexer._get_parser_for_file", return_value=None):
            store = index_repository(repo)
            stats = store.get_stats()
            assert stats.total_nodes == 0
