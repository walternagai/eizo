"""Servidor MCP para Eizō usando FastMCP.

Expõe ferramentas de consulta ao grafo de conhecimento para agentes LLM
via Model Context Protocol (MCP).
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from eizo.graph.store import GraphStore
from eizo.queries import impact as impact_q
from eizo.queries import search as search_q
from eizo.queries import trace as trace_q


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
    ) -> str:
        """Busca símbolos no grafo de conhecimento por nome.

        Args:
            query: Nome ou padrão de busca.
            kind: Filtrar por tipo (function, class, method, import).
            language: Filtrar por linguagem (python, typescript).
            limit: Limite de resultados (padrão: 20).
        """
        results = search_q.search_symbols(store, query, kind=kind, language=language, limit=limit)
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

    return mcp


def serve_mcp(store: GraphStore, port: int = 8765) -> None:
    """Inicia o servidor MCP."""
    mcp = create_server(store, port)
    mcp.run(transport="sse")
