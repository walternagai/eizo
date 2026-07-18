"""Testes para exportação do grafo em HTML (visualização 3D).

Cobre:
- queries/export.py: export_html()
- CLI: eizo export html
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from eizo.cli import main
from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore
from eizo.queries.export import export_html

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
             language="python", line_start=1, docstring="Classe base Animal."),
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


def _extract_graph_data(html: str) -> dict:
    """Extrai o payload JSON embutido no HTML gerado."""
    match = re.search(
        r'<script id="graph-data" type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    assert match is not None, "bloco <script id=\"graph-data\"> não encontrado"
    return json.loads(match.group(1))


# ─── export_html ───────────────────────────────────────────────


class TestExportHtml:
    """Testa export_html()."""

    def test_html_basic_structure(self, export_store: GraphStore) -> None:
        """HTML tem estrutura básica e o script do 3d-force-graph embutido."""
        result = export_html(export_store)
        assert "<!DOCTYPE html>" in result
        assert "ForceGraph3D" in result
        assert '<div id="graph">' in result

    def test_html_contains_all_nodes(self, export_store: GraphStore) -> None:
        """Payload embutido inclui todos os nós esperados."""
        result = export_html(export_store)
        data = _extract_graph_data(result)
        ids = {n["id"] for n in data["nodes"]}
        assert ids == {"animal", "dog", "speak", "main", "create_dog"}

    def test_html_contains_all_edges(self, export_store: GraphStore) -> None:
        """Payload embutido inclui todas as arestas esperadas."""
        result = export_html(export_store)
        data = _extract_graph_data(result)
        pairs = {(link["source"], link["target"], link["kind"]) for link in data["links"]}
        assert ("dog", "animal", "inherits") in pairs
        assert ("main", "create_dog", "calls") in pairs

    def test_html_node_includes_docstring_and_location(self, export_store: GraphStore) -> None:
        """Nós carregam docstring, file_path e linhas para o painel de detalhes."""
        result = export_html(export_store)
        data = _extract_graph_data(result)
        animal = next(n for n in data["nodes"] if n["id"] == "animal")
        assert animal["docstring"] == "Classe base Animal."
        assert animal["file_path"] == "a.py"
        assert animal["line_start"] == 1

    def test_html_degree_computation(self, export_store: GraphStore) -> None:
        """'val' (grau) soma entrada + saída dentro do subgrafo exportado."""
        result = export_html(export_store)
        data = _extract_graph_data(result)
        degrees = {n["id"]: n["val"] for n in data["nodes"]}
        # dog: inherits->animal (saída) + create_dog->dog (entrada) + dog->speak (saída) = 3
        assert degrees["dog"] == 3
        # animal: apenas dog->animal (entrada) = 1
        assert degrees["animal"] == 1
        # main: apenas main->create_dog (saída) = 1
        assert degrees["main"] == 1

    def test_html_kind_filter(self, export_store: GraphStore) -> None:
        """Filtro de kind limita nós no payload embutido."""
        result = export_html(export_store, kind="class")
        data = _extract_graph_data(result)
        ids = {n["id"] for n in data["nodes"]}
        assert ids == {"animal", "dog"}

    def test_html_language_filter(self, export_store: GraphStore) -> None:
        """Filtro de linguagem limita nós no payload embutido."""
        export_store.upsert_nodes([
            Node(id="ts_dog", name="Dog", kind="class", file_path="dog.ts", language="typescript"),
        ])
        result = export_html(export_store, language="typescript")
        data = _extract_graph_data(result)
        ids = {n["id"] for n in data["nodes"]}
        assert ids == {"ts_dog"}

    def test_html_limit(self, export_store: GraphStore) -> None:
        """Limite restringe a quantidade de nós no payload embutido."""
        result = export_html(export_store, limit=2)
        data = _extract_graph_data(result)
        assert len(data["nodes"]) == 2

    def test_html_edge_kind_filter(self, export_store: GraphStore) -> None:
        """Filtro de edge_kinds restringe arestas no payload embutido."""
        result = export_html(export_store, edge_kinds=frozenset({"calls"}))
        data = _extract_graph_data(result)
        kinds = {link["kind"] for link in data["links"]}
        assert kinds == {"calls"}

    def test_html_escapes_script_close_tag(self, export_store: GraphStore) -> None:
        """Docstring contendo '</script>' não deve quebrar o parsing do HTML."""
        export_store.upsert_nodes([
            Node(id="evil", name="evil", kind="function", file_path="e.py",
                 language="python", docstring="</script><script>alert(1)</script>"),
        ])
        result = export_html(export_store)
        assert "<script>alert(1)</script>" not in result
        data = _extract_graph_data(result)
        evil = next(n for n in data["nodes"] if n["id"] == "evil")
        assert evil["docstring"] == "</script><script>alert(1)</script>"


# ─── CLI ───────────────────────────────────────────────────────


class TestExportHtmlCli:
    """Testa `eizo export html` via CLI."""

    def test_cli_export_html_writes_file(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text(
            'def foo():\n    """Diz oi."""\n    return "oi"\n'
        )

        runner = CliRunner()
        init_result = runner.invoke(main, ["init", str(repo)])
        assert init_result.exit_code == 0

        out_file = tmp_path / "graph.html"
        export_result = runner.invoke(main, ["export", "html", "--repo", str(repo), "-o", str(out_file)])
        assert export_result.exit_code == 0
        assert out_file.exists()

        content = out_file.read_text(encoding="utf-8")
        assert "ForceGraph3D" in content
        data = _extract_graph_data(content)
        assert any(n["name"] == "foo" for n in data["nodes"])
