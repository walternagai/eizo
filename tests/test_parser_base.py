"""Testes para parser/base.py."""

from __future__ import annotations

from pathlib import Path

from eizo.parser.base import BaseParser


class TestBaseParser:
    """Testes para a classe base abstrata."""

    def test_should_parse_by_extension(self) -> None:
        """should_parse deve reconhecer extensões suportadas."""

        class FakeParser(BaseParser):
            @property
            def language(self) -> str:
                return "fake"

            @property
            def extensions(self) -> set[str]:
                return {".foo", ".bar"}

            def parse_file(self, file_path: Path, source: str) -> tuple[list, list]:  # noqa: ARG002
                return [], []

        parser = FakeParser()

        assert parser.should_parse(Path("test.foo")) is True
        assert parser.should_parse(Path("test.bar")) is True
        assert parser.should_parse(Path("test.py")) is False
        assert parser.should_parse(Path("test")) is False
