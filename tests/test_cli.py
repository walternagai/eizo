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
        no_fts = runner.invoke(main, ["search", "pagamento", "--path", str(repo)])
        assert "Nenhum resultado" in no_fts.output

        result = runner.invoke(
            main, ["search", "pagamento", "--full-text", "--path", str(repo)]
        )
        assert result.exit_code == 0
        assert "process" in result.output


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

    def test_trace_empty_state(self, tmp_path: Path) -> None:
        """Símbolo sem callers/callees mostra empty-state para ambos."""
        repo = Path(tmp_path)
        (repo / "test.py").write_text("def loner(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store)

        runner = CliRunner()
        result = runner.invoke(main, ["trace", "loner", "--path", str(repo)])
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
        result = runner.invoke(main, ["trace", "caller", "--path", str(repo)])
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
        result = runner.invoke(main, ["trace", "foo", "--path", str(repo)])
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
        result = runner.invoke(main, ["trace", "a", "--path", str(repo), "--depth", "5"])
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
            main, ["trace", "helper", "--direction", "incoming", "--path", str(repo)]
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
