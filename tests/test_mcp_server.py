"""Testes para o servidor MCP (eizo.mcp.server).

Cobre create_server(), _node_to_dict(), as 5 tools registradas e serve_mcp().
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore
from eizo.mcp.server import _node_to_dict, create_server, serve_mcp

# ─── _node_to_dict ───


class TestNodeToDict:
    """Testa a conversão de Node para dict serializável."""

    def test_node_to_dict_all_fields(self) -> None:
        """Converte um Node completo com todos os campos preenchidos."""
        node = Node(
            id="abc123",
            name="my_func",
            kind="function",
            file_path="src/module.py",
            language="python",
            line_start=10,
            line_end=20,
            docstring="Faz algo útil.",
            code_snippet="def my_func(): pass",
        )
        result = _node_to_dict(node)
        assert result == {
            "id": "abc123",
            "name": "my_func",
            "kind": "function",
            "file_path": "src/module.py",
            "language": "python",
            "line_start": 10,
            "line_end": 20,
            "docstring": "Faz algo útil.",
            "code_snippet": "def my_func(): pass",
        }

    def test_node_to_dict_minimal_fields(self) -> None:
        """Converte um Node com campos opcionais vazios."""
        node = Node(
            id="x",
            name="x",
            kind="import",
            file_path="a.py",
            language="python",
            line_start=1,
            line_end=1,
            docstring=None,
            code_snippet=None,
        )
        result = _node_to_dict(node)
        assert result["docstring"] is None
        assert result["code_snippet"] is None
        assert result["id"] == "x"


# ─── create_server ───


@pytest.fixture
def populated_store(store: GraphStore) -> GraphStore:
    """GraphStore com nós e arestas para testar as tools MCP."""
    store.upsert_nodes([
        Node(id="core", name="core", kind="function", file_path="core.py",
             language="python", line_start=1, line_end=10,
             docstring="Núcleo.", code_snippet="def core(): pass"),
        Node(id="middle", name="middle", kind="function", file_path="middle.py",
             language="python", line_start=1, line_end=5,
             docstring=None, code_snippet="def middle(): core()"),
        Node(id="top", name="top", kind="class", file_path="top.py",
             language="python", line_start=1, line_end=20,
             docstring="Topo.", code_snippet="class top: ..."),
    ])
    store.upsert_edges([
        Edge(source_id="middle", target_id="core", kind="calls"),
        Edge(source_id="top", target_id="middle", kind="calls"),
    ])
    return store


def _get_tool_fn(mcp: object, name: str) -> object:
    """Extrai a função original de uma tool registrada no FastMCP."""
    tool = mcp._tool_manager._tools[name]  # type: ignore[attr-defined]
    return tool.fn


class TestCreateServer:
    """Testa create_server() e o registro das 5 tools."""

    def test_create_server_returns_fastmcp(self, store: GraphStore) -> None:
        """create_server retorna uma instância de FastMCP."""
        from mcp.server.fastmcp import FastMCP

        mcp = create_server(store, port=12345)
        assert isinstance(mcp, FastMCP)

    def test_all_five_tools_registered(self, store: GraphStore) -> None:
        """As tools MCP devem estar registradas com os nomes esperados."""
        mcp = create_server(store, port=12345)
        tool_names = set(mcp._tool_manager._tools.keys())
        assert tool_names == {
            "search_symbols",
            "get_symbol_context",
            "trace_call_path",
            "analyze_impact",
            "get_architecture",
            "find_dead_code_symbols",
            "get_hotspots",
        }

    # ─── search_symbols ───

    def test_search_symbols_returns_json(self, populated_store: GraphStore) -> None:
        """search_symbols retorna JSON com lista de nós."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "search_symbols")
        result = fn(query="core")
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "core"
        assert parsed[0]["kind"] == "function"

    def test_search_symbols_with_kind_filter(self, populated_store: GraphStore) -> None:
        """search_symbols filtra por kind."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "search_symbols")
        result = fn(query="", kind="class")
        parsed = json.loads(result)
        assert all(n["kind"] == "class" for n in parsed)
        assert any(n["name"] == "top" for n in parsed)

    def test_search_symbols_with_language_filter(self, populated_store: GraphStore) -> None:
        """search_symbols filtra por language."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "search_symbols")
        result = fn(query="", language="python")
        parsed = json.loads(result)
        assert all(n["language"] == "python" for n in parsed)

    def test_search_symbols_empty_query(self, populated_store: GraphStore) -> None:
        """search_symbols com query vazia retorna todos (até o limite)."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "search_symbols")
        result = fn(query="", limit=10)
        parsed = json.loads(result)
        assert len(parsed) == 3

    def test_search_symbols_no_results(self, populated_store: GraphStore) -> None:
        """search_symbols sem matches retorna lista vazia."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "search_symbols")
        result = fn(query="zzz_nothing_zzz")
        parsed = json.loads(result)
        assert parsed == []

    # ─── get_symbol_context ───

    def test_get_symbol_context(self, populated_store: GraphStore) -> None:
        """get_symbol_context retorna contexto do símbolo serializado em JSON.

        Nota: o server usa json.dumps(default=str), então objetos Node/Edge
        são serializados como string (repr do dataclass). Validamos a estrutura
        e que o nó foi encontrado (não é None).
        """
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "get_symbol_context")
        result = fn(node_id="core", depth=1)
        parsed = json.loads(result)
        assert "node" in parsed
        assert parsed["node"] is not None
        assert "incoming" in parsed
        assert "outgoing" in parsed
        assert "file_nodes" in parsed

    def test_get_symbol_context_depth2(self, populated_store: GraphStore) -> None:
        """get_symbol_context com depth=2 inclui chaves deeper_*."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "get_symbol_context")
        result = fn(node_id="middle", depth=2)
        parsed = json.loads(result)
        assert "deeper_incoming" in parsed
        assert "deeper_outgoing" in parsed

    def test_get_symbol_context_unknown_id(self, populated_store: GraphStore) -> None:
        """get_symbol_context com ID inexistente retorna node=None."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "get_symbol_context")
        result = fn(node_id="nonexistent_id_xyz", depth=1)
        parsed = json.loads(result)
        assert parsed["node"] is None
        assert parsed["incoming"] == []

    # ─── trace_call_path ───

    def test_trace_call_path_outgoing(self, populated_store: GraphStore) -> None:
        """trace_call_path com direction=outgoing."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "trace_call_path")
        result = fn(symbol_name="top", direction="outgoing")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert parsed["symbol"] is not None

    def test_trace_call_path_incoming(self, populated_store: GraphStore) -> None:
        """trace_call_path com direction=incoming."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "trace_call_path")
        result = fn(symbol_name="core", direction="incoming")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_trace_call_path_both(self, populated_store: GraphStore) -> None:
        """trace_call_path com direction=both."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "trace_call_path")
        result = fn(symbol_name="middle", direction="both", max_depth=3)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_trace_call_path_unknown_symbol(self, populated_store: GraphStore) -> None:
        """trace_call_path com símbolo inexistente."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "trace_call_path")
        result = fn(symbol_name="zzz_unknown_zzz")
        parsed = json.loads(result)
        assert parsed["symbol"] is None

    # ─── analyze_impact ───

    def test_analyze_impact(self, populated_store: GraphStore) -> None:
        """analyze_impact retorna cadeia de impacto."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "analyze_impact")
        result = fn(symbol_name="core", max_depth=3)
        parsed = json.loads(result)
        assert "symbol" in parsed
        assert "impact_chain" in parsed

    def test_analyze_impact_unknown_symbol(self, populated_store: GraphStore) -> None:
        """analyze_impact com símbolo inexistente."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "analyze_impact")
        result = fn(symbol_name="zzz_unknown_zzz")
        parsed = json.loads(result)
        assert parsed["symbol"] is None

    # ─── get_architecture ───

    def test_get_architecture(self, populated_store: GraphStore) -> None:
        """get_architecture retorna estatísticas do grafo."""
        mcp = create_server(populated_store, port=12345)
        fn = _get_tool_fn(mcp, "get_architecture")
        result = fn()
        parsed = json.loads(result)
        assert parsed["total_nodes"] == 3
        assert parsed["total_edges"] == 2
        assert "by_language" in parsed
        assert "by_kind" in parsed
        assert "by_edge_kind" in parsed
        assert "db_size_bytes" in parsed

    def test_get_architecture_empty_store(self, store: GraphStore) -> None:
        """get_architecture com store vazio retorna zeros."""
        mcp = create_server(store, port=12345)
        fn = _get_tool_fn(mcp, "get_architecture")
        result = fn()
        parsed = json.loads(result)
        assert parsed["total_nodes"] == 0
        assert parsed["total_edges"] == 0


# ─── serve_mcp ───


class TestServeMcp:
    """Testa serve_mcp() — deve criar servidor e chamar run()."""

    def test_serve_mcp_calls_run(self, store: GraphStore) -> None:
        """serve_mcp cria o servidor e chama mcp.run(transport='sse') por padrão."""
        with patch("eizo.mcp.server.create_server") as mock_create:
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            serve_mcp(store, port=9999)
            mock_create.assert_called_once_with(store, 9999)
            mock_mcp.run.assert_called_once_with(transport="sse")

    def test_serve_mcp_stdio_transport(self, store: GraphStore) -> None:
        """serve_mcp com transport='stdio' chama mcp.run(transport='stdio')."""
        with patch("eizo.mcp.server.create_server") as mock_create:
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            serve_mcp(store, port=9999, transport="stdio")
            mock_create.assert_called_once_with(store, 9999)
            mock_mcp.run.assert_called_once_with(transport="stdio")
