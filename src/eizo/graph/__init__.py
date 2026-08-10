"""Camada de persistência do grafo de conhecimento.

API pública estável (ver deprecation policy em AGENTS.md/README.md):
``GraphStore``, ``Node``, ``Edge``, ``GraphStats`` e ``DEFINITION_KINDS``.

Módulos internos — ``graph.schema`` (schema/migrações SQLite) e helpers
com underscore em ``graph.store`` — não fazem parte da API pública: podem
mudar sem aviso entre versões.
"""

from __future__ import annotations

from eizo.graph.models import DEFINITION_KINDS, Edge, GraphStats, Node
from eizo.graph.store import GraphStore

__all__ = [
    "DEFINITION_KINDS",
    "Edge",
    "GraphStats",
    "GraphStore",
    "Node",
]
