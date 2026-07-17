"""Servidor MCP para Eizō usando FastMCP.

Expõe ferramentas de consulta ao grafo de conhecimento para agentes LLM
via Model Context Protocol (MCP).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from eizo.graph.store import GraphStore
from eizo.queries import impact as impact_q
from eizo.queries import search as search_q
from eizo.queries import trace as trace_q
from eizo.queries.analysis import find_dead_code, find_hotspots

# Teto de segurança para parâmetros `limit` das tools — evita que um cliente
# MCP peça um resultset arbitrariamente grande (ex: limit=1_000_000).
_MAX_LIMIT = 500


def _clamp_limit(limit: int) -> int:
    """Restringe `limit` ao intervalo [1, _MAX_LIMIT]."""
    return max(1, min(limit, _MAX_LIMIT))


def _node_to_dict(node: Any) -> dict[str, Any]:
    """Converte um Node para dict serializável."""
    return {
        "id": node.id,
        "name": node.name,
        "kind": node.kind,
        "file_path": node.file_path,
        "language": node.language,
        "line_start": node.line_start,
        "line_end": node.line_end,
        "docstring": node.docstring,
        "code_snippet": node.code_snippet,
    }


def create_server(store: GraphStore, port: int = 8765) -> FastMCP:
    """Cria e configura o servidor MCP."""
    mcp = FastMCP("eizo", port=port)

    @mcp.tool()
    def search_symbols(
        query: str,
        kind: str | None = None,
        language: str | None = None,
        limit: int = 20,
        full_text: bool = False,
    ) -> str:
        """Busca símbolos no grafo de conhecimento.

        Args:
            query: Nome ou padrão de busca.
            kind: Filtrar por tipo (function, class, method, import).
            language: Filtrar por linguagem (python, typescript).
            limit: Limite de resultados (padrão: 20).
            full_text: Se True, busca full-text (FTS5) sobre nome + docstring
                + code_snippet, ranqueada por relevância — útil para buscar
                por conteúdo mencionado em docstrings/código. Padrão (False)
                busca por substring no nome, que cobre camelCase e snake_case.
        """
        results = search_q.search_symbols(
            store, query, kind=kind, language=language, limit=_clamp_limit(limit), full_text=full_text
        )
        return json.dumps([_node_to_dict(n) for n in results], indent=2, default=str)

    @mcp.tool()
    def get_symbol_context(node_id: str, depth: int = 1) -> str:
        """Retorna o contexto completo de um símbolo (vizinhança, arquivo).

        Args:
            node_id: ID do nó no grafo.
            depth: Profundidade da vizinhança (1 = diretos, 2 = expandido).
        """
        result = search_q.get_symbol_context(store, node_id, depth=depth)
        return json.dumps(result, indent=2, default=str)

    @mcp.tool()
    def trace_call_path(
        symbol_name: str,
        direction: str = "both",
        max_depth: int = 5,
    ) -> str:
        """Traça o caminho de chamadas de/para um símbolo.

        Args:
            symbol_name: Nome do símbolo.
            direction: incoming (quem chama), outgoing (quem é chamado), both.
            max_depth: Profundidade máxima (padrão: 5).
        """
        result = trace_q.trace_call_path(store, symbol_name, direction=direction, max_depth=max_depth)
        return json.dumps(result, indent=2, default=str)

    @mcp.tool()
    def analyze_impact(symbol_name: str, max_depth: int = 3) -> str:
        """Analisa o impacto de mudança em um símbolo.

        Args:
            symbol_name: Nome do símbolo.
            max_depth: Profundidade máxima (padrão: 3).
        """
        result = impact_q.analyze_impact(store, symbol_name, max_depth=max_depth)
        return json.dumps(result, indent=2, default=str)

    @mcp.tool()
    def get_architecture() -> str:
        """Retorna visão arquitetural do repositório (estatísticas do grafo)."""
        stats = store.get_stats()
        return json.dumps({
            "total_nodes": stats.total_nodes,
            "total_edges": stats.total_edges,
            "total_files": stats.total_files,
            "by_language": stats.by_language,
            "by_kind": stats.by_kind,
            "by_edge_kind": stats.by_edge_kind,
            "db_size_bytes": stats.db_size_bytes,
        }, indent=2, default=str)

    @mcp.tool()
    def find_dead_code_symbols(
        limit: int = 100,
        entrypoints: list[str] | None = None,
    ) -> str:
        """Encontra símbolos definidos sem nenhum caller/import (dead code).

        Args:
            limit: Máximo de resultados (padrão: 100).
            entrypoints: Nomes de entrypoints a excluir (ex: ['main', 'serve']).
                Se None, usa padrões: main, run, serve, app, create_app, etc.
        """
        eps = frozenset(entrypoints) if entrypoints else None
        results = find_dead_code(store, entrypoints=eps, limit=_clamp_limit(limit))
        return json.dumps([_node_to_dict(n) for n in results], indent=2, default=str)

    @mcp.tool()
    def get_hotspots(
        limit: int = 20,
        min_references: int = 2,
    ) -> str:
        """Retorna símbolos mais referenciados (hotspots de acoplamento).

        Args:
            limit: Máximo de resultados (padrão: 20).
            min_references: Mínimo de referências para aparecer (padrão: 2).
        """
        results = find_hotspots(store, limit=_clamp_limit(limit), min_references=min_references)
        return json.dumps([
            {"node": _node_to_dict(r["node"]), "reference_count": r["reference_count"]}
            for r in results
        ], indent=2, default=str)

    return mcp


def serve_mcp(store: GraphStore, port: int = 8765, transport: Literal["sse", "stdio"] = "sse") -> None:
    """Inicia o servidor MCP.

    Args:
        store: GraphStore com o grafo de conhecimento.
        port: Porta para transporte SSE (ignorado se transport='stdio').
        transport: Tipo de transporte — 'sse' (HTTP) ou 'stdio' (local).
    """
    mcp = create_server(store, port)
    mcp.run(transport=transport)
