"""Testes para exportação do grafo (DOT, Mermaid, JSON).

Cobre:
- queries/export.py: export_dot(), export_mermaid(), export_json()
- CLI: eizo export dot|mermaid|json
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from eizo.cli import main
from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore
from eizo.queries.export import export_dot, export_json, export_mermaid

# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def export_store(store: GraphStore) -> GraphStore:
    """Store com grafo para testar exportação.

    Estrutura:
        Animal (class) --> Dog (class, inherits Animal)
        Dog.speak (method)
        main (function) --> create_dog (function, calls)
        create_dog --> Dog (calls)
    """
    store.upsert_nodes([
        Node(id="animal", name="Animal", kind="class", file_path="a.py",
             language="python", line_start=1),
        Node(id="dog", name="Dog", kind="class", file_path="b.py",
             language="python", line_start=10),
        Node(id="speak", name="speak", kind="method", file_path="b.py",
             language="python", line_start=15),
        Node(id="main", name="main", kind="function", file_path="c.py",
             language="python", line_start=1),
        Node(id="create_dog", name="create_dog", kind="function", file_path="d.py",
             language="python", line_start=20),
    ])
    store.upsert_edges([
        Edge(source_id="dog", target_id="animal", kind="inherits"),
        Edge(source_id="main", target_id="create_dog", kind="calls"),
        Edge(source_id="create_dog", target_id="dog", kind="calls"),
        Edge(source_id="dog", target_id="speak", kind="contains"),
    ])
    return store


# ─── export_dot ────────────────────────────────────────────────


class TestExportDot:
    """Testa export_dot()."""

    def test_dot_basic_structure(self, export_store: GraphStore) -> None:
        """DOT tem estrutura básica: digraph, nós, arestas."""
        result = export_dot(export_store)
        assert "digraph eizo {" in result
        assert "}" in result
        assert "rankdir=LR" in result

    def test_dot_contains_all_nodes(self, export_store: GraphStore) -> None:
        """DOT inclui todos os nós como declarações."""
        result = export_dot(export_store)
        # IDs sanitizados: n_ + id com hifens -> underscores
        assert "n_animal" in result
        assert "n_dog" in result
        assert "n_main" in result

    def test_dot_contains_node_labels(self, export_store: GraphStore) -> None:
        """DOT inclui labels dos nós com os nomes."""
        result = export_dot(export_store)
        assert 'label="Animal"' in result
        assert 'label="Dog"' in result
        assert 'label="main"' in result

    def test_dot_contains_edges(self, export_store: GraphStore) -> None:
        """DOT inclui arestas com labels."""
        result = export_dot(export_store)
        assert "->" in result
        assert 'label="inherits"' in result
        assert 'label="calls"' in result

    def test_dot_class_shape_is_box(self, export_store: GraphStore) -> None:
        """Classes têm shape=box e fillcolor=lightblue."""
        result = export_dot(export_store)
        # Animal e Dog são classes
        assert "shape=box" in result
        assert "fillcolor=lightblue" in result

    def test_dot_function_shape_is_ellipse(self, export_store: GraphStore) -> None:
        """Functions têm shape=ellipse e fillcolor=lightgreen."""
        result = export_dot(export_store)
        assert "shape=ellipse" in result
        assert "fillcolor=lightgreen" in result

    def test_dot_kind_filter(self, export_store: GraphStore) -> None:
        """Filtro de kind limita nós."""
        result = export_dot(export_store, kind="class")
        assert 'label="Animal"' in result
        assert 'label="Dog"' in result
        # main não é class
        assert 'label="main"' not in result

    def test_dot_language_filter(self, export_store: GraphStore) -> None:
        """Filtro de linguagem limita nós."""
        # Adiciona nó TS
        export_store.upsert_nodes([
            Node(id="ts_func", name="ts_func", kind="function", file_path="x.ts",
                 language="typescript"),
        ])
        result = export_dot(export_store, language="typescript")
        assert 'label="ts_func"' in result
        assert 'label="main"' not in result

    def test_dot_edge_kinds_filter(self, export_store: GraphStore) -> None:
        """Filtro de edge_kinds limita arestas."""
        result = export_dot(export_store, edge_kinds=frozenset({"inherits"}))
        assert 'label="inherits"' in result
        assert 'label="calls"' not in result

    def test_dot_limit(self, export_store: GraphStore) -> None:
        """Limit restringe número de nós."""
        result = export_dot(export_store, limit=2)
        # Com 2 nós, não deve ter todas as arestas
        # Conta declarações de nó (linhas com n_ e label)
        node_lines = [line for line in result.splitlines() if "label=" in line and "shape=" in line]
        assert len(node_lines) <= 2

    def test_dot_empty_store(self, store: GraphStore) -> None:
        """DOT de store vazio tem estrutura mas sem nós."""
        result = export_dot(store)
        assert "digraph eizo {" in result
        assert "->" not in result


# ─── export_mermaid ────────────────────────────────────────────


class TestExportMermaid:
    """Testa export_mermaid()."""

    def test_mermaid_flowchart_basic(self, export_store: GraphStore) -> None:
        """Mermaid flowchart tem header correto."""
        result = export_mermaid(export_store)
        assert result.startswith("flowchart LR")

    def test_mermaid_flowchart_contains_nodes(self, export_store: GraphStore) -> None:
        """Mermaid inclui todos os nós."""
        result = export_mermaid(export_store)
        assert '"Animal"' in result
        assert '"Dog"' in result
        assert '"main"' in result

    def test_mermaid_flowchart_contains_edges(self, export_store: GraphStore) -> None:
        """Mermaid inclui arestas com labels."""
        result = export_mermaid(export_store)
        assert "-->|inherits|" in result
        assert "-->|calls|" in result

    def test_mermaid_class_diagram(self, export_store: GraphStore) -> None:
        """Mermaid classDiagram tem header correto."""
        result = export_mermaid(export_store, diagram_type="classDiagram")
        assert result.startswith("classDiagram")
        assert "class " in result

    def test_mermaid_class_diagram_inheritance_arrow(self, export_store: GraphStore) -> None:
        """classDiagram usa --|> para inherits."""
        result = export_mermaid(export_store, diagram_type="classDiagram")
        assert "--|>" in result

    def test_mermaid_kind_filter(self, export_store: GraphStore) -> None:
        """Filtro de kind limita nós."""
        result = export_mermaid(export_store, kind="class")
        assert '"Animal"' in result
        assert '"main"' not in result

    def test_mermaid_empty_store(self, store: GraphStore) -> None:
        """Mermaid de store vazio tem header mas sem nós."""
        result = export_mermaid(store)
        assert result.startswith("flowchart LR")


# ─── export_json ───────────────────────────────────────────────


class TestExportJson:
    """Testa export_json()."""

    def test_json_valid(self, export_store: GraphStore) -> None:
        """JSON é válido e parseable."""
        result = export_json(export_store)
        data = json.loads(result)
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_json_contains_all_nodes(self, export_store: GraphStore) -> None:
        """JSON inclui todos os nós."""
        result = export_json(export_store)
        data = json.loads(result)
        names = {n["name"] for n in data["nodes"]}
        assert "Animal" in names
        assert "Dog" in names
        assert "main" in names

    def test_json_contains_all_edges(self, export_store: GraphStore) -> None:
        """JSON inclui todas as arestas."""
        result = export_json(export_store)
        data = json.loads(result)
        assert len(data["edges"]) == 4  # 4 arestas na fixture

    def test_json_node_fields(self, export_store: GraphStore) -> None:
        """Cada nó no JSON tem os campos esperados."""
        result = export_json(export_store)
        data = json.loads(result)
        node = data["nodes"][0]
        assert "id" in node
        assert "name" in node
        assert "kind" in node
        assert "file_path" in node
        assert "language" in node

    def test_json_edge_fields(self, export_store: GraphStore) -> None:
        """Cada aresta no JSON tem os campos esperados."""
        result = export_json(export_store)
        data = json.loads(result)
        edge = data["edges"][0]
        assert "source_id" in edge
        assert "target_id" in edge
        assert "kind" in edge

    def test_json_kind_filter(self, export_store: GraphStore) -> None:
        """Filtro de kind limita nós."""
        result = export_json(export_store, kind="class")
        data = json.loads(result)
        kinds = {n["kind"] for n in data["nodes"]}
        assert kinds == {"class"}

    def test_json_empty_store(self, store: GraphStore) -> None:
        """JSON de store vazio tem arrays vazios."""
        result = export_json(store)
        data = json.loads(result)
        assert data["nodes"] == []
        assert data["edges"] == []


# ─── CLI: eizo export ──────────────────────────────────────────


class TestCliExport:
    """Testa o comando 'eizo export'."""

    def test_export_dot_to_stdout(self, tmp_path: Path) -> None:
        """export dot imprime na stdout."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(main, ["export", "dot", "--path", str(repo)])
        assert result.exit_code == 0
        assert "digraph" in result.output

    def test_export_mermaid_to_stdout(self, tmp_path: Path) -> None:
        """export mermaid imprime na stdout."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(main, ["export", "mermaid", "--path", str(repo)])
        assert result.exit_code == 0
        assert "flowchart" in result.output

    def test_export_json_to_stdout(self, tmp_path: Path) -> None:
        """export json imprime JSON válido na stdout."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(main, ["export", "json", "--path", str(repo)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "nodes" in parsed
        assert "edges" in parsed

    def test_export_to_file(self, tmp_path: Path) -> None:
        """export -o escreve em arquivo."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        output_file = tmp_path / "graph.dot"
        runner = CliRunner()
        result = runner.invoke(
            main, ["export", "dot", "-o", str(output_file), "--path", str(repo)]
        )
        assert result.exit_code == 0
        assert "exportado" in result.output
        assert output_file.exists()
        assert "digraph" in output_file.read_text()

    def test_export_with_kind_filter(self, tmp_path: Path) -> None:
        """export com --kind filtra nós."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text(
            "class MyClass: pass\ndef my_func(): pass\n"
        )
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(
            main, ["export", "json", "--kind", "class", "--path", str(repo)]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        kinds = {n["kind"] for n in parsed["nodes"]}
        assert "class" in kinds
        assert "function" not in kinds

    def test_export_mermaid_class_diagram(self, tmp_path: Path) -> None:
        """export mermaid --diagram-type classDiagram."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("class Foo: pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        runner = CliRunner()
        result = runner.invoke(
            main, ["export", "mermaid", "--diagram-type", "classDiagram", "--path", str(repo)]
        )
        assert result.exit_code == 0
        assert "classDiagram" in result.output

    def test_export_empty_store(self, tmp_path: Path) -> None:
        """export em store vazio não falha."""
        runner = CliRunner()
        result = runner.invoke(main, ["export", "dot", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "digraph" in result.output

    def test_export_invalid_format(self, tmp_path: Path) -> None:
        """Formato inválido retorna erro."""
        runner = CliRunner()
        result = runner.invoke(main, ["export", "invalid", "--path", str(tmp_path)])
        assert result.exit_code != 0
