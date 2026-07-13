# AGENTS.md — Eizō (映像)

Codebase Knowledge Graph CLI. Python 3.10+, Click, Tree-sitter, SQLite, FastMCP.

## Commands

```bash
make install     # pip install -e ".[dev]"
make test        # pytest -v
make lint        # ruff check src/eizo/ tests/
make typecheck   # mypy src/eizo/
make check       # lint + typecheck + test
make coverage    # pytest --cov=src/eizo --cov-report=term-missing
```

## Entry points

- `eizo` CLI: `eizo.cli:main` (Click group, 7 commands)
- `python -m eizo`: `eizo/__main__.py` → `cli.main()`
- `eizo.mcp.server.serve_mcp()`: FastMCP server, invoked via `eizo mcp`

## Architecture

```
src/eizo/
├── cli.py          # Click commands (init, search, trace, impact, arch, mcp, status)
├── indexer.py      # Orchestrator: scan repo → parse files → persist to SQLite
├── graph/
│   ├── models.py   # Node, Edge, GraphStats dataclasses
│   ├── schema.py   # SQLite schema, get_db_path(), open_db()
│   └── store.py    # GraphStore CRUD (upsert, search, trace, stats)
├── parser/
│   ├── base.py     # Abstract BaseParser
│   ├── python.py   # Tree-sitter Python parser
│   └── typescript.py # Tree-sitter TS/JS parser
├── queries/
│   ├── search.py   # search_symbols(), get_symbol_context()
│   ├── trace.py    # trace_call_path() — call graph traversal
│   └── impact.py   # analyze_impact() — dependency chain
└── mcp/
    └── server.py   # FastMCP server (5 tools)
```

## Tree-sitter quirks

- `tree-sitter>=0.23`: `language()` returns a **PyCapsule**, not a `Language` object.
  Must wrap: `Language(capsule)`.
- Python inheritance field is `superclasses` (not `bases`).
- TypeScript inheritance: `class_heritage` → `extends_clause` → `identifier`.
- Docstring extraction: remove quote chars from the `string` node manually.

## MCP quirks

- Uses `FastMCP` (not low-level `Server`). Tools registered via `@mcp.tool()` decorator.
- Port set in constructor: `FastMCP("eizo", port=8765)`, not as attribute.
- Run with `mcp.run(transport="sse")`.

## SQLite

- DB stored at `{repo}/.eizo/graph.db`. WAL mode + foreign keys ON.
- Schema: `nodes` (id, name, kind, file_path, language, line_start/end, docstring, code_snippet, metadata) + `edges` (source_id, target_id, kind, metadata).
- Node IDs: SHA-256(`{file_path}:{name}:{line}`)[:16].

## Testing

- `store` fixture: `GraphStore(tmp_path)` — SQLite in temp dir.
- `sample_python_file` / `sample_ts_file`: string fixtures for parser tests.
- `sample_python_repo`: creates real dir tree for indexer tests.
- Coverage gate: 70%. `cli.py` and `__main__.py` are untested (0%).
- `asyncio_mode = auto` in pytest config.

## Conventions

- `from __future__ import annotations` in every file.
- Type hints on all functions (params + return).
- No `print()` — use `rich.console.Console`.
- Imports: stdlib → third-party → local, alphabetical within groups.
- Ruff: line-length 120, select E/F/I/N/W/UP/B/SIM/ARG/C4.
- Mypy: strict mode, `ignore_missing_imports = true` (tree-sitter, mcp).
- Code in English, docstrings/comments in Portuguese BR.
