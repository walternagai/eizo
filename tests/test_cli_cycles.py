"""Testes para o comando 'eizo cycles' (CLI)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from eizo.cli import main
from eizo.indexer import index_repository


class TestCliCycles:
    """Testa o comando 'eizo cycles'."""

    def test_cycles_no_results(self, indexed_empty_repo: Path) -> None:
        """Sem ciclos, mostra mensagem de sucesso."""
        runner = CliRunner()
        result = runner.invoke(main, ["cycles", "--repo", str(indexed_empty_repo)])
        assert result.exit_code == 0
        assert "Nenhum ciclo" in result.output

    def test_cycles_detects_two_file_cycle(self, tmp_path: Path) -> None:
        """Dois arquivos que se importam mutuamente aparecem como ciclo."""
        repo = Path(tmp_path)
        (repo / "a.py").write_text("from b import beta\ndef alfa():\n    beta()\n")
        (repo / "b.py").write_text("from a import alfa\ndef beta():\n    pass\n")
        index_repository(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["cycles", "--repo", str(repo)])

        assert result.exit_code == 0
        assert "Ciclos de import detectados (1)" in result.output
        assert "a.py" in result.output
        assert "b.py" in result.output

    def test_cycles_no_cycle_with_normal_imports(self, tmp_path: Path) -> None:
        """Import numa via só (a -> b, sem volta) não é ciclo."""
        repo = Path(tmp_path)
        (repo / "a.py").write_text("from b import beta\ndef alfa():\n    beta()\n")
        (repo / "b.py").write_text("def beta():\n    pass\n")
        index_repository(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["cycles", "--repo", str(repo)])

        assert result.exit_code == 0
        assert "Nenhum ciclo" in result.output

    def test_cycles_json_format(self, tmp_path: Path) -> None:
        """--output-format json retorna a estrutura files/path."""
        repo = Path(tmp_path)
        (repo / "a.py").write_text("from b import beta\ndef alfa():\n    beta()\n")
        (repo / "b.py").write_text("from a import alfa\ndef beta():\n    pass\n")
        index_repository(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "cycles", "--repo", str(repo)])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        assert {Path(f).name for f in parsed[0]["files"]} == {"a.py", "b.py"}
        assert parsed[0]["path"][0] == parsed[0]["path"][-1]

    def test_cycles_unindexed_repo_fails(self, tmp_path: Path) -> None:
        """Repositório não indexado é erro acionável, como os demais comandos de consulta."""
        runner = CliRunner()
        result = runner.invoke(main, ["cycles", "--repo", str(tmp_path)])
        assert result.exit_code == 1
        assert "não indexado" in result.output
