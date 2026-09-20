"""Testes para exportação do grafo (DOT, Mermaid, JSON, SVG, PNG).

Cobre:
- queries/export.py: export_dot(), export_mermaid(), export_json(),
  export_svg(), export_png()
- CLI: eizo export dot|mermaid|json|svg|png
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from eizo.cli import main
from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore
from eizo.queries.export import (
    export_architecture_mermaid,
    export_dot,
    export_json,
    export_mermaid,
    export_png,
    export_svg,
)

# ─── Fixtures ──────────────────────────────────────────────────

requires_dot = pytest.mark.skipif(
    shutil.which("dot") is None,
    reason="graphviz (dot) não instalado — instale com: apt install graphviz",
)

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

    def test_mermaid_class_diagram_braces_balanced(self, export_store: GraphStore) -> None:
        """Cada bloco 'class X {' deve fechar com uma única '}' (não '}}')."""
        result = export_mermaid(export_store, diagram_type="classDiagram")
        lines = result.splitlines()
        assert "}}" not in result
        opens = sum(1 for line in lines if line.strip().endswith("{"))
        closes = sum(1 for line in lines if line.strip() == "}")
        assert opens > 0
        assert opens == closes

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


# ─── export_svg / export_png (graphviz) ───────────────────────


class TestExportSvgPng:
    """Testa export_svg() e export_png() — pulam se `dot` não estiver instalado."""

    @requires_dot
    def test_svg_starts_with_xml_or_svg(self, export_store: GraphStore) -> None:
        """SVG começa com <?xml ou <svg (conteúdo válido de imagem vetorial)."""
        result = export_svg(export_store)
        assert isinstance(result, bytes)
        head = result[:200].decode("utf-8", errors="replace")
        assert head.lstrip().startswith("<?xml") or head.lstrip().startswith("<svg")

    @requires_dot
    def test_svg_contains_node_labels(self, export_store: GraphStore) -> None:
        """SVG inclui os labels dos nós do grafo."""
        result = export_svg(export_store)
        assert b"Animal" in result
        assert b"Dog" in result

    @requires_dot
    def test_png_magic_bytes(self, export_store: GraphStore) -> None:
        """PNG tem magic bytes \\x89PNG."""
        result = export_png(export_store)
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    @requires_dot
    def test_svg_kind_filter(self, export_store: GraphStore) -> None:
        """Filtro de kind limita nós no SVG."""
        result = export_svg(export_store, kind="class")
        assert b"Animal" in result
        assert b"main" not in result

    def test_svg_without_dot_raises(self, export_store: GraphStore, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sem `dot` no PATH, export_svg levanta RuntimeError com instrução clara."""
        monkeypatch.setattr("eizo.queries.export.shutil.which", lambda _name: None)
        with pytest.raises(RuntimeError, match="graphviz"):
            export_svg(export_store)

    def test_png_without_dot_raises(self, export_store: GraphStore, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sem `dot` no PATH, export_png levanta RuntimeError com instrução clara."""
        monkeypatch.setattr("eizo.queries.export.shutil.which", lambda _name: None)
        with pytest.raises(RuntimeError, match="graphviz"):
            export_png(export_store)


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
        result = runner.invoke(main, ["export", "dot", "--repo", str(repo)])
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
        result = runner.invoke(main, ["export", "mermaid", "--repo", str(repo)])
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
        result = runner.invoke(main, ["export", "json", "--repo", str(repo)])
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
            main, ["export", "dot", "-o", str(output_file), "--repo", str(repo)]
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
            main, ["export", "json", "--kind", "class", "--repo", str(repo)]
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
            main, ["export", "mermaid", "--diagram-type", "classDiagram", "--repo", str(repo)]
        )
        assert result.exit_code == 0
        assert "classDiagram" in result.output

    def test_export_empty_store(self, indexed_empty_repo: Path) -> None:
        """export em store vazio não falha."""
        runner = CliRunner()
        result = runner.invoke(main, ["export", "dot", "--repo", str(indexed_empty_repo)])
        assert result.exit_code == 0
        assert "digraph" in result.output

    def test_export_invalid_format(self, tmp_path: Path) -> None:
        """Formato inválido retorna erro."""
        runner = CliRunner()
        result = runner.invoke(main, ["export", "invalid", "--repo", str(tmp_path)])
        assert result.exit_code != 0

    @requires_dot
    def test_export_svg_to_file(self, tmp_path: Path) -> None:
        """export svg -o escreve arquivo SVG válido."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        output_file = tmp_path / "graph.svg"
        runner = CliRunner()
        result = runner.invoke(
            main, ["export", "svg", "-o", str(output_file), "--repo", str(repo)]
        )
        assert result.exit_code == 0
        assert "exportado" in result.output
        assert output_file.exists()
        head = output_file.read_bytes()[:200].decode("utf-8", errors="replace")
        assert head.lstrip().startswith("<?xml") or head.lstrip().startswith("<svg")

    @requires_dot
    def test_export_png_to_file(self, tmp_path: Path) -> None:
        """export png -o escreve arquivo PNG com magic bytes."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        output_file = tmp_path / "graph.png"
        runner = CliRunner()
        result = runner.invoke(
            main, ["export", "png", "-o", str(output_file), "--repo", str(repo)]
        )
        assert result.exit_code == 0
        assert "exportado" in result.output
        assert output_file.exists()
        assert output_file.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_export_svg_without_dot_errors(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """export svg sem `dot` no PATH falha com exit code != 0 e mensagem clara."""
        from eizo.indexer import index_repository

        repo = Path(tmp_path)
        (repo / "test.py").write_text("def foo(): pass\n")
        store = GraphStore(repo)
        index_repository(repo, store, force=True)

        monkeypatch.setattr("eizo.queries.export.shutil.which", lambda _name: None)
        runner = CliRunner()
        result = runner.invoke(main, ["export", "svg", "--repo", str(repo)])
        assert result.exit_code != 0
        assert "graphviz" in result.output


# ─── export_architecture_mermaid ───────────────────────────────


class TestExportArchitectureMermaid:
    """Testa export_architecture_mermaid()."""

    def test_architecture_mermaid_header(self, export_store: GraphStore) -> None:
        """Diagrama arquitetural começa com 'graph TD'."""
        result = export_architecture_mermaid(export_store)
        assert result.startswith("graph TD")

    def test_architecture_mermaid_contains_subgraphs(self, export_store: GraphStore) -> None:
        """Diagrama contém subgraphs representando camadas."""
        result = export_architecture_mermaid(export_store)
        assert "subgraph" in result
        assert "Other" in result

    def test_architecture_mermaid_contains_components(self, export_store: GraphStore) -> None:
        """Diagrama lista componentes (arquivos) dentro das camadas."""
        result = export_architecture_mermaid(export_store)
        # A fixture tem a.py, b.py, c.py, d.py — todos cairão em 'other'
        for stem in ("a", "b", "c", "d"):
            assert stem in result

    def test_architecture_mermaid_contains_descriptions(self, export_store: GraphStore) -> None:
        """Diagrama inclui descrições de componentes."""
        result = export_architecture_mermaid(export_store)
        assert "component" in result

    def test_architecture_mermaid_stats_subgraph(self, export_store: GraphStore) -> None:
        """Diagrama inclui subgraph de estatísticas."""
        result = export_architecture_mermaid(export_store)
        assert "subgraph Stats" in result
        assert "Total nodes" in result
        assert "Total edges" in result

    def test_architecture_mermaid_empty_store(self, store: GraphStore) -> None:
        """Store vazio retorna diagrama com mensagem informativa."""
        result = export_architecture_mermaid(store)
        assert result.startswith("graph TD")
        assert "Grafo vazio" in result

    def test_architecture_mermaid_component_edges_with_known_paths(self) -> None:
        """Dependências entre componentes aparecem quando paths são reconhecidos."""
        from eizo.graph.models import Edge, Node

        s = GraphStore(Path("/tmp/eizo_arch_test_" + str(id(self))))
        s.upsert_nodes([
            Node(id="q1", name="search", kind="function", file_path="src/queries/search.py", language="python"),
            Node(id="g1", name="store", kind="class", file_path="src/graph/store.py", language="python"),
        ])
        s.upsert_edges([Edge(source_id="q1", target_id="g1", kind="calls")])
        result = export_architecture_mermaid(s)
        assert "-->" in result
        assert "comp_queries_search_py" in result
        assert "comp_graph_store_py" in result
        s.close()


# ─── Determinismo e escaping (P2 da revisão repo-full-review) ──


class TestExportDeterminism:
    """Dois exports do mesmo grafo produzem a MESMA string."""

    def _make_store(self, tmp_path: Path) -> GraphStore:
        store = GraphStore(tmp_path)
        store.upsert_nodes([
            Node(id="a1", name="zebra", kind="function", file_path="b.py", language="python", line_start=1, line_end=1),
            Node(id="a2", name="alpha", kind="function", file_path="b.py", language="python", line_start=2, line_end=2),
            Node(id="a3", name="beta", kind="function", file_path="a.py", language="python", line_start=1, line_end=1),
            Node(
                id="a4", name="caller", kind="function", file_path="c.py",
                language="python", line_start=1, line_end=1,
            ),
        ])
        store.upsert_edges([
            Edge(source_id="a4", target_id="a1", kind="calls"),
            Edge(source_id="a4", target_id="a2", kind="calls"),
            Edge(source_id="a3", target_id="a1", kind="calls"),
        ])
        return store

    def test_json_deterministic(self, tmp_path: Path) -> None:
        """export_json: mesma string em duas chamadas no mesmo store."""
        store = self._make_store(tmp_path)
        assert export_json(store) == export_json(store)

    def test_json_deterministic_after_reupsert(self, tmp_path: Path) -> None:
        """Re-upsert (INSERT OR REPLACE reatribui rowid) não muda o export."""
        store = self._make_store(tmp_path)
        # Nota: re-upsert de um nó apaga arestas incidentes (FK CASCADE no
        # REPLACE — defeito conhecido, fora do escopo desta task); re-upsert
        # só valida a estabilidade da ORDENAÇÃO, sem arestas incidentes.
        store.upsert_nodes([
            Node(id="a5", name="delta", kind="function", file_path="d.py", language="python", line_start=1, line_end=1),
            Node(id="a6", name="echo", kind="function", file_path="d.py", language="python", line_start=2, line_end=2),
        ])
        before = export_json(store)
        store.upsert_nodes([
            Node(id="a5", name="delta", kind="function", file_path="d.py", language="python", line_start=1, line_end=1),
            Node(id="a6", name="echo", kind="function", file_path="d.py", language="python", line_start=2, line_end=2),
        ])
        assert export_json(store) == before

    def test_json_ordering_is_file_then_name(self, tmp_path: Path) -> None:
        """Ordem estável: file_path depois name (não rowid)."""
        store = self._make_store(tmp_path)
        data = json.loads(export_json(store))
        names = [n["name"] for n in data["nodes"]]
        assert names == ["beta", "alpha", "zebra", "caller"]

    def test_dot_and_mermaid_deterministic(self, tmp_path: Path) -> None:
        """dot e mermaid usam os mesmos fetchers — também estáveis."""
        store = self._make_store(tmp_path)
        assert export_dot(store) == export_dot(store)
        assert export_mermaid(store) == export_mermaid(store)


class TestDotLabelEscaping:
    """Labels DOT com caracteres especiais produzem DOT válido."""

    def test_quotes_backslash_newline_escaped(self, tmp_path: Path) -> None:
        store = GraphStore(tmp_path)
        store.upsert_nodes([
            Node(id="x1", name='we"ird\\name', kind="function", file_path="x.py",
                 language="python", line_start=1, line_end=1),
            Node(id="x2", name="line\nbreak", kind="function", file_path="x.py",
                 language="python", line_start=2, line_end=2),
        ])
        result = export_dot(store)
        # Nenhuma aspa crua do nome dentro do label — todas escapadas
        assert 'label="we\\"ird\\\\name"' in result
        assert 'label="line\\nbreak"' in result

    def test_mermaid_class_diagram_comment_newline(self, tmp_path: Path) -> None:
        """Nome com newline não quebra o comentário %% do classDiagram."""
        store = GraphStore(tmp_path)
        store.upsert_nodes([
            Node(id="y1", name="My\nClass", kind="class", file_path="y.py",
                 language="python", line_start=1, line_end=1),
        ])
        result = export_mermaid(store, diagram_type="classDiagram")
        assert "%% My Class" in result  # newline virou espaço
        assert "My\nClass" not in result
