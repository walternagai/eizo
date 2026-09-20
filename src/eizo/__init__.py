"""Eizō — Codebase Knowledge Graph CLI.

API pública estável (ver deprecation policy em AGENTS.md e docs/api.md):
``GraphStore``, ``Node``, ``Edge``, ``GraphStats``, ``DEFINITION_KINDS``,
``index_repository``, as funções de consulta de ``eizo.queries`` e
``create_server``/``serve_mcp`` de ``eizo.mcp.server``.

O CLI (``eizo.cli``) é estável por contrato de CLI (comandos/opções), não
por API Python. Submódulos como ``eizo.graph.schema``,
``eizo.graph.store`` (diretamente), ``eizo.parser.*``, ``eizo.indexer``
(diretamente) e ``eizo.static`` são internos: podem mudar sem aviso entre
versões — use sempre os re-exports deste pacote.
"""

from __future__ import annotations

from eizo.graph import DEFINITION_KINDS, Edge, GraphStats, GraphStore, Node
from eizo.indexer import index_repository
from eizo.queries import (
    analyze_impact,
    compute_symbol_metrics,
    diff_against_ref,
    diff_between_refs,
    export_architecture_mermaid,
    export_dot,
    export_html,
    export_json,
    export_mermaid,
    export_png,
    export_svg,
    find_dead_code,
    find_dependency_path,
    find_hotspots,
    find_import_cycles,
    get_symbol_context,
    search_symbols,
    trace_call_path,
)

__version__ = "1.0.1"

__all__ = [
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
]
