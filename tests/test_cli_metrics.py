"""Testes para o comando 'eizo metrics' (CLI)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from eizo.cli import main
from eizo.indexer import index_repository


class TestCliMetrics:
    """Testa o comando 'eizo metrics'."""

    def test_metrics_symbol_not_found(self, indexed_empty_repo: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["metrics", "inexistente", "--repo", str(indexed_empty_repo)])
        assert result.exit_code == 0
        assert "Nenhuma definição encontrada" in result.output

    def test_metrics_shows_table(self, tmp_path: Path) -> None:
        repo = Path(tmp_path)
        (repo / "lib.py").write_text("def helper():\n    return 1\n")
        (repo / "main.py").write_text("from lib import helper\ndef run():\n    helper()\n")
        index_repository(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["metrics", "helper", "--repo", str(repo)])

        assert result.exit_code == 0
        assert "helper" in result.output
        assert "Fan-in" in result.output
        assert "Fan-out" in result.output

    def test_metrics_json_format(self, tmp_path: Path) -> None:
        repo = Path(tmp_path)
        (repo / "lib.py").write_text("def helper():\n    return 1\n")
        index_repository(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "metrics", "helper", "--repo", str(repo)])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        assert parsed[0]["node"]["name"] == "helper"
        assert "fan_in" in parsed[0]
        assert "fan_out" in parsed[0]
        assert "loc" in parsed[0]

    def test_metrics_unindexed_repo_fails(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["metrics", "foo", "--repo", str(tmp_path)])
        assert result.exit_code == 1
        assert "não indexado" in result.output
