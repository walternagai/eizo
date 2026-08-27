"""Testes de contrato para a superfície pública do Eizō."""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest

import eizo
import eizo.graph as graph
import eizo.queries as queries
from eizo import Edge, GraphStore, Node
from eizo.cli import main

EXPECTED_ROOT_EXPORTS = frozenset({
    "DEFINITION_KINDS",
    "Edge",
    "GraphStats",
    "GraphStore",
    "Node",
    "__version__",
    "analyze_impact",
    "compute_symbol_metrics",
    "diff_against_ref",
    "diff_between_refs",
    "export_architecture_mermaid",
    "export_dot",
    "export_html",
    "export_json",
    "export_mermaid",
    "export_png",
    "export_svg",
    "find_dead_code",
    "find_dependency_path",
    "find_hotspots",
    "find_import_cycles",
    "get_symbol_context",
    "index_repository",
    "search_symbols",
    "trace_call_path",
})

EXPECTED_GRAPH_EXPORTS = frozenset({
    "DEFINITION_KINDS",
    "Edge",
    "GraphStats",
    "GraphStore",
    "Node",
})

EXPECTED_QUERY_EXPORTS = frozenset({
    "analyze_impact",
    "compute_symbol_metrics",
    "diff_against_ref",
    "diff_between_refs",
    "export_architecture_mermaid",
    "export_dot",
    "export_html",
    "export_json",
    "export_mermaid",
    "export_png",
    "export_svg",
    "find_dead_code",
    "find_dependency_path",
    "find_hotspots",
    "find_import_cycles",
    "get_symbol_context",
    "search_symbols",
    "trace_call_path",
})

PUBLIC_MODULES = (
    (eizo, EXPECTED_ROOT_EXPORTS),
    (graph, EXPECTED_GRAPH_EXPORTS),
    (queries, EXPECTED_QUERY_EXPORTS),
)

EXPECTED_CLI_COMMANDS = frozenset({
    "arch",
    "architecture",
    "cycles",
    "dead",
    "diff",
    "export",
    "hotspots",
    "impact",
    "init",
    "mcp",
    "metrics",
    "search",
    "status",
    "trace",
    "watch",
    "why",
})

CLI_COMMAND_OPTIONS = {
    "init": frozenset({"path", "repo_path", "rebuild", "force", "dry_run"}),
    "search": frozenset({"query", "kind", "language", "limit", "full_text", "repo_path"}),
    "trace": frozenset({"symbol", "direction", "depth", "repo_path"}),
    "export": frozenset({
        "format", "kind", "language", "limit", "edge_kinds", "diagram_type", "output", "repo_path",
    }),
}

API_DOC = Path(__file__).parents[1] / "docs" / "api.md"


@pytest.mark.parametrize(("module", "expected"), PUBLIC_MODULES)
def test_public_all_matches_contract(module: ModuleType, expected: frozenset[str]) -> None:
    """Os módulos públicos não podem remover ou renomear exports sem decisão."""
    actual = frozenset(module.__dict__["__all__"])
    assert actual == expected
    assert all(hasattr(module, name) for name in expected)


def test_root_reexports_share_the_public_objects() -> None:
    """O pacote raiz deve reexportar os mesmos objetos dos subpacotes públicos."""
    assert eizo.GraphStore is graph.GraphStore
    assert eizo.Node is graph.Node
    assert eizo.Edge is graph.Edge
    assert eizo.search_symbols is queries.search_symbols
    assert eizo.export_json is queries.export_json


def test_public_exports_are_documented() -> None:
    """Cada símbolo público deve aparecer na documentação de API."""
    documentation = API_DOC.read_text(encoding="utf-8")
    documented_names = EXPECTED_ROOT_EXPORTS | {"create_server", "serve_mcp"}
    for name in documented_names:
        assert f"`{name}`" in documentation, name


def test_cli_command_surface_matches_contract() -> None:
    """A lista de comandos CLI estáveis deve permanecer compatível."""
    assert frozenset(main.commands) == EXPECTED_CLI_COMMANDS


def test_cli_global_options_match_contract() -> None:
    """Opções globais documentadas devem continuar disponíveis."""
    actual = {param.name for param in main.params}
    expected = {
        "output_format",
        "no_color",
        "color",
        "config_path",
        "install_completion",
        "show_completion",
        "verbosity",
        "quiet",
    }
    assert expected <= actual


@pytest.mark.parametrize(("command_name", "expected"), CLI_COMMAND_OPTIONS.items())
def test_cli_command_options_match_contract(command_name: str, expected: frozenset[str]) -> None:
    """Opções essenciais de comandos estáveis não podem desaparecer."""
    command = main.commands[command_name]
    actual = {param.name for param in command.params}
    assert expected <= actual


def test_public_export_json_shape(store: GraphStore) -> None:
    """O export JSON mantém os contêineres e campos básicos documentados."""
    store.upsert_nodes([
        Node(id="source", name="source", kind="function", file_path="a.py", language="python"),
        Node(id="target", name="target", kind="function", file_path="b.py", language="python"),
    ])
    store.upsert_edge(Edge(source_id="source", target_id="target", kind="calls"))

    exported = json.loads(eizo.export_json(store))

    assert set(exported) == {"nodes", "edges"}
    assert {"id", "name", "kind", "file_path", "language"} <= set(exported["nodes"][0])
    assert set(exported["edges"][0]) == {"source_id", "target_id", "kind"}
