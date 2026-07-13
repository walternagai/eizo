"""Modelos de domínio do grafo de conhecimento."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Node:
    """Um nó no grafo de conhecimento — representa um símbolo do código."""

    id: str
    name: str
    kind: str  # function, class, method, file, module
    file_path: str
    language: str
    line_start: int | None = None
    line_end: int | None = None
    docstring: str | None = None
    code_snippet: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    """Uma aresta no grafo de conhecimento — representa uma relação entre símbolos."""

    source_id: str
    target_id: str
    kind: str  # calls, imports, inherits, contains
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphStats:
    """Estatísticas do grafo de conhecimento."""

    total_nodes: int = 0
    total_edges: int = 0
    by_language: dict[str, int] = field(default_factory=dict)
    by_kind: dict[str, int] = field(default_factory=dict)
    by_edge_kind: dict[str, int] = field(default_factory=dict)
    total_files: int = 0
    db_size_bytes: int = 0
