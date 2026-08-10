"""Consultas sobre o grafo de conhecimento.

API pública estável (ver deprecation policy em AGENTS.md/README.md): as
funções de consulta exportadas abaixo. ``queries.search`` também expõe
``get_symbol_context`` (pública). Qualquer outra função com prefixo
``_`` é interna e pode mudar sem aviso.
"""

from __future__ import annotations

from eizo.queries.analysis import find_dead_code, find_hotspots
from eizo.queries.cycles import find_import_cycles
from eizo.queries.diff import diff_against_ref, diff_between_refs
from eizo.queries.export import (
    export_architecture_mermaid,
    export_dot,
    export_html,
    export_json,
    export_mermaid,
    export_png,
    export_svg,
)
from eizo.queries.impact import analyze_impact
from eizo.queries.metrics import compute_symbol_metrics
from eizo.queries.search import get_symbol_context, search_symbols
from eizo.queries.trace import trace_call_path
from eizo.queries.why import find_dependency_path

__all__ = [
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
]
