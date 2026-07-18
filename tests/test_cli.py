"""Testes para CLI (Click commands via CliRunner)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
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

    def test_init_dry_run(self, tmp_path: Path) -> None:
        """Init --dry-run lista arquivos sem persistir."""
        runner = CliRunner()
        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        result = runner.invoke(main, ["init", "--dry-run", str(repo)])
        assert result.exit_code == 0
        assert "Dry-run" in result.output
        assert "test.py" in result.output
        # Não deve criar banco
        assert not (repo / ".eizo" / "graph.db").exists()

    def test_init_dry_run_json(self, tmp_path: Path) -> None:
        """Init --dry-run --output-format json retorna lista em JSON."""
        runner = CliRunner()
        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        result = runner.invoke(main, ["--output-format", "json", "init", "--dry-run", str(repo)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["dry_run"] is True
        assert any("test.py" in f for f in parsed["files"])


class TestCliSearch:
    """Testes para o comando 'eizo search'."""

    def test_search_no_results(self, tmp_path: Path) -> None:
        """Search sem resultados deve mostrar mensagem."""
        runner = CliRunner()
        result = runner.invoke(main, ["search", "nonexistent", "--repo", str(tmp_path)])
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
        result = runner.invoke(main, ["search", "hello", "--repo", str(repo)])
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
            "--language", "python", "--repo", str(repo),
        ])
        assert result.exit_code == 0
        assert "foo" in result.output


    def test_search_full_text_finds_by_docstring(self, tmp_path: Path) -> None:
        """--full-text busca em docstring, não só no nome."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text(
            'def process():\n    """Valida um pagamento antes de processar."""\n    pass\n'
        )
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        # Sem --full-text, "pagamento" não bate com o nome "process".
        no_fts = runner.invoke(main, ["search", "pagamento", "--repo", str(repo)])
        assert "Nenhum resultado" in no_fts.output

        result = runner.invoke(
            main, ["search", "pagamento", "--full-text", "--repo", str(repo)]
        )
        assert result.exit_code == 0
        assert "process" in result.output


class TestCliTrace:
    """Testes para o comando 'eizo trace'."""

    def test_trace_not_found(self, tmp_path: Path) -> None:
        """Trace de símbolo inexistente."""
        runner = CliRunner()
        result = runner.invoke(main, ["trace", "nonexistent", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "não encontrado" in result.output

    def test_trace_found(self, tmp_path: Path) -> None:
        """Trace de símbolo existente."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def caller(): callee()\ndef callee(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["trace", "caller", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Call graph" in result.output

    def test_trace_empty_state(self, tmp_path: Path) -> None:
        """Símbolo sem callers/callees mostra empty-state para ambos."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def loner(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["trace", "loner", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Nenhum caller encontrado" in result.output
        assert "Nenhuma callee encontrada" in result.output

    def test_trace_summary_line(self, tmp_path: Path) -> None:
        """Trace sempre mostra linha de sumário ao final."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def caller(): callee()\ndef callee(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["trace", "caller", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "caller(s)" in result.output
        assert "callee(s)" in result.output
        assert "profundidade máx" in result.output

    def test_trace_docstring_shown(self, tmp_path: Path) -> None:
        """Docstring do símbolo raiz aparece como primeira linha."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text(
            'def foo():\n    """Faz algo importante."""\n    pass\n'
        )
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["trace", "foo", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Faz algo importante" in result.output

    def test_trace_cycle_rendered(self, tmp_path: Path) -> None:
        """Ciclo é renderizado com marcador (cycle) na árvore.

        Usa o store diretamente para criar uma edge B->A (ciclo), já que o
        parser atual cria nós 'call' intermediários em vez de ligar funções
        diretamente.
        """
        from eizo.graph.models import Edge, Node

        repo = Path(tmp_path)
        store = GraphStore(repo)
        store.upsert_nodes([
            Node(id="a", name="a", kind="function", file_path=str(repo / "a.py"), language="python"),
            Node(id="b", name="b", kind="function", file_path=str(repo / "b.py"), language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="a", target_id="b", kind="calls"),
            Edge(source_id="b", target_id="a", kind="calls"),
        ])

        runner = CliRunner()
        result = runner.invoke(main, ["trace", "a", "--repo", str(repo), "--depth", "5"])
        assert result.exit_code == 0
        assert "(cycle)" in result.output

    def test_trace_incoming_shown(self, tmp_path: Path) -> None:
        """Direction incoming mostra callers e sumário conta callers.

        Usa o store diretamente para criar edges user_a->helper e user_b->helper,
        já que o parser atual cria nós 'call' intermediários.
        """
        from eizo.graph.models import Edge, Node

        repo = Path(tmp_path)
        store = GraphStore(repo)
        store.upsert_nodes([
            Node(id="helper", name="helper", kind="function", file_path=str(repo / "helper.py"), language="python"),
            Node(id="user_a", name="user_a", kind="function", file_path=str(repo / "user_a.py"), language="python"),
            Node(id="user_b", name="user_b", kind="function", file_path=str(repo / "user_b.py"), language="python"),
        ])
        store.upsert_edges([
            Edge(source_id="user_a", target_id="helper", kind="calls"),
            Edge(source_id="user_b", target_id="helper", kind="calls"),
        ])

        runner = CliRunner()
        result = runner.invoke(
            main, ["trace", "helper", "--direction", "incoming", "--repo", str(repo)]
        )
        assert result.exit_code == 0
        assert "Quem chama" in result.output
        # Sumário deve mostrar 2 callers
        assert "2 caller(s)" in result.output


class TestCliImpact:
    """Testes para o comando 'eizo impact'."""

    def test_impact_not_found(self, tmp_path: Path) -> None:
        """Impact de símbolo inexistente."""
        runner = CliRunner()
        result = runner.invoke(main, ["impact", "nonexistent", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "não encontrado" in result.output

    def test_impact_found(self, tmp_path: Path) -> None:
        """Impact de símbolo existente."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def helper(): pass\ndef user(): helper()\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["impact", "helper", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Análise de impacto" in result.output


class TestCliArch:
    """Testes para o comando 'eizo arch'."""

    def test_arch_empty(self, tmp_path: Path) -> None:
        """Arch em repositório vazio."""
        runner = CliRunner()
        result = runner.invoke(main, ["arch", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "Grafo vazio" in result.output

    def test_arch_with_data(self, tmp_path: Path) -> None:
        """Arch com dados."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["arch", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Visão Arquitetural" in result.output


class TestCliStatus:
    """Testes para o comando 'eizo status'."""

    def test_status_empty(self, tmp_path: Path) -> None:
        """Status em repositório vazio."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "Grafo vazio" in result.output

    def test_status_with_data(self, tmp_path: Path) -> None:
        """Status com dados."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["status", "--repo", str(repo)])
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


class TestCliCompletion:
    """Testes para shell completion."""

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_show_completion(self, shell: str) -> None:
        """--show-completion <shell> emite script de completion."""
        runner = CliRunner()
        result = runner.invoke(main, ["--show-completion", shell])
        assert result.exit_code == 0
        assert "_EIZO_COMPLETE" in result.output

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_install_completion(self, shell: str) -> None:
        """--install-completion <shell> emite script de completion."""
        runner = CliRunner()
        result = runner.invoke(main, ["--install-completion", shell])
        assert result.exit_code == 0
        assert "_EIZO_COMPLETE" in result.output

    def test_completion_invalid_shell(self) -> None:
        """Shell inválido retorna erro."""
        runner = CliRunner()
        result = runner.invoke(main, ["--show-completion", "invalid"])
        assert result.exit_code != 0


class TestCliEnvVars:
    """Testes para variáveis de ambiente EIZO_* e NO_COLOR."""

    def test_env_output_format(self, tmp_path: Path, monkeypatch: Any) -> None:
        """EIZO_OUTPUT_FORMAT muda saída para JSON."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        monkeypatch.setenv("EIZO_OUTPUT_FORMAT", "json")
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--repo", str(repo)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total_nodes" in parsed

    def test_env_no_color(self, tmp_path: Path, monkeypatch: Any) -> None:
        """EIZO_NO_COLOR=1 desativa cores."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        monkeypatch.setenv("EIZO_NO_COLOR", "1")
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Status do Grafo" in result.output
        assert "\x1b[" not in result.output

    def test_env_no_color_global(self, tmp_path: Path, monkeypatch: Any) -> None:
        """NO_COLOR (global) também desativa cores."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        monkeypatch.setenv("NO_COLOR", "1")
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "\x1b[" not in result.output

    def test_env_repo(self, tmp_path: Path, monkeypatch: Any) -> None:
        """EIZO_REPO define o repo padrão."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        monkeypatch.setenv("EIZO_REPO", str(repo))
        runner = CliRunner()
        result = runner.invoke(main, ["--output-format", "json", "status"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["total_nodes"] == 2

    def test_env_config(self, tmp_path: Path, monkeypatch: Any) -> None:
        """EIZO_CONFIG aponta para arquivo de config alternativo."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        alt_config = tmp_path / "env.json"
        alt_config.write_text(json.dumps({"output_format": "json"}))

        monkeypatch.setenv("EIZO_CONFIG", str(alt_config))
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--repo", str(repo)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total_nodes" in parsed

    def test_env_cli_overrides_env(self, tmp_path: Path, monkeypatch: Any) -> None:
        """CLI explícito sobrescreve variável de ambiente."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        monkeypatch.setenv("EIZO_OUTPUT_FORMAT", "json")
        runner = CliRunner()
        result = runner.invoke(
            main, ["--output-format", "table", "status", "--repo", str(repo)]
        )
        assert result.exit_code == 0
        assert "Status do Grafo" in result.output

    def test_env_limit(self, tmp_path: Path, monkeypatch: Any) -> None:
        """EIZO_LIMIT define limite de resultados do search."""
        repo = Path(tmp_path)
        for name in ("a", "b", "c"):
            (repo / f"{name}.py").write_text(f"def {name}(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        monkeypatch.setenv("EIZO_LIMIT", "2")
        runner = CliRunner()
        result = runner.invoke(main, ["search", "a", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "2 resultado(s)" in result.output

    def test_env_invalid_limit_ignored(self, tmp_path: Path, monkeypatch: Any) -> None:
        """EIZO_LIMIT inválido cai no default do Click sem erro."""
        repo = Path(tmp_path)
        for name in ("a", "b", "c"):
            (repo / f"{name}.py").write_text(f"def {name}(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        monkeypatch.setenv("EIZO_LIMIT", "not-a-number")
        runner = CliRunner()
        result = runner.invoke(main, ["search", "a", "--repo", str(repo)])
        assert result.exit_code == 0
        # Default do search é 20; como a query 'a' retorna 2 resultados,
        # basta confirmar que não houve erro e há resultados.
        assert "resultado(s)" in result.output


class TestCliLogging:
    """Testes para logging/verbosity."""

    def test_verbose_info(self, tmp_path: Path, caplog: Any) -> None:
        """-v emite mensagens INFO."""
        runner = CliRunner()
        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        with caplog.at_level("INFO", logger="eizo"):
            result = runner.invoke(main, ["-v", "init", "--dry-run", str(repo)])
        assert result.exit_code == 0
        assert "INFO" in caplog.text

    def test_very_verbose_debug(self, tmp_path: Path, caplog: Any) -> None:
        """-vv emite mensagens DEBUG."""
        runner = CliRunner()
        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        with caplog.at_level("DEBUG", logger="eizo"):
            result = runner.invoke(main, ["-vv", "init", "--dry-run", str(repo)])
        assert result.exit_code == 0
        assert any(record.levelno == logging.DEBUG for record in caplog.records)

    def test_quiet_suppresses_info(self, tmp_path: Path, caplog: Any) -> None:
        """--quiet mantém apenas WARNING+."""
        runner = CliRunner()
        repo = Path(tmp_path)
        (repo / "test.py").write_text("x = 1\n")
        with caplog.at_level("WARNING", logger="eizo"):
            result = runner.invoke(main, ["--quiet", "-v", "init", "--dry-run", str(repo)])
        assert result.exit_code == 0
        assert not any(record.levelno == logging.INFO for record in caplog.records)


class TestCliArchitecture:
    """Testes para o comando 'eizo architecture' (alias de 'arch')."""

    def test_architecture_empty(self, tmp_path: Path) -> None:
        """architecture em store vazio mostra mensagem."""
        runner = CliRunner()
        result = runner.invoke(main, ["architecture", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "Grafo vazio" in result.output

    def test_architecture_with_data(self, tmp_path: Path) -> None:
        """architecture mostra visão arquitetural (tabela)."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["architecture", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Visão Arquitetural" in result.output

    def test_architecture_to_file(self, tmp_path: Path) -> None:
        """architecture -o escreve arquivo Mermaid."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        output_file = tmp_path / "arch.mmd"
        runner = CliRunner()
        result = runner.invoke(
            main, ["architecture", "-o", str(output_file), "--repo", str(repo)]
        )
        assert result.exit_code == 0
        assert "exportado" in result.output
        assert output_file.exists()
        assert "graph TD" in output_file.read_text()

    def test_architecture_json_format(self, tmp_path: Path) -> None:
        """architecture --output-format json retorna stats em JSON."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(
            main, ["--output-format", "json", "architecture", "--repo", str(repo)]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total_nodes" in parsed


class TestCliConfig:
    """Testes para arquivo de configuração .eizo/config.json e --config."""

    def test_config_output_format_from_eizo_config_json(self, tmp_path: Path) -> None:
        """config.json com output_format='json' muda saída de status para JSON."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        eizo_dir = repo / ".eizo"
        eizo_dir.mkdir(exist_ok=True)
        (eizo_dir / "config.json").write_text(json.dumps({"output_format": "json"}))

        runner = CliRunner()
        result = runner.invoke(main, ["status", "--repo", str(repo)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total_nodes" in parsed

    def test_config_limit_from_eizo_config_json(self, tmp_path: Path) -> None:
        """config.json com limit é aplicado ao search."""
        repo = Path(tmp_path)
        for name in ("a", "b", "c"):
            (repo / f"{name}.py").write_text(f"def {name}(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        eizo_dir = repo / ".eizo"
        eizo_dir.mkdir(exist_ok=True)
        (eizo_dir / "config.json").write_text(json.dumps({"limit": 2}))

        runner = CliRunner()
        result = runner.invoke(main, ["search", "a", "--repo", str(repo)])
        assert result.exit_code == 0
        # Apenas 2 resultados devido ao limit do config
        assert "2 resultado(s)" in result.output

    def test_config_cli_overrides_config(self, tmp_path: Path) -> None:
        """CLI explícito (--output-format json) sobrescreve config.json table."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        eizo_dir = repo / ".eizo"
        eizo_dir.mkdir(exist_ok=True)
        (eizo_dir / "config.json").write_text(json.dumps({"output_format": "table"}))

        runner = CliRunner()
        result = runner.invoke(
            main, ["--output-format", "json", "status", "--repo", str(repo)]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total_nodes" in parsed

    def test_config_alternative_path(self, tmp_path: Path) -> None:
        """--config aponta para arquivo fora do repo."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        alt_config = tmp_path / "alt.json"
        alt_config.write_text(json.dumps({"output_format": "json"}))

        runner = CliRunner()
        result = runner.invoke(
            main, ["--config", str(alt_config), "status", "--repo", str(repo)]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total_nodes" in parsed

    def test_config_invalid_json_warns_and_ignores(self, tmp_path: Path) -> None:
        """config.json inválido gera aviso e usa defaults."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        eizo_dir = repo / ".eizo"
        eizo_dir.mkdir(exist_ok=True)
        (eizo_dir / "config.json").write_text("not-json")

        runner = CliRunner()
        result = runner.invoke(main, ["status", "--repo", str(repo)])
        assert result.exit_code == 0
        assert "Aviso: config inválido" in result.output
        assert "Status do Grafo" in result.output
