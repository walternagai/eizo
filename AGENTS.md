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

- `eizo` CLI: `eizo.cli:main` (Click group, 10 commands)
- `python -m eizo`: `eizo/__main__.py` → `cli.main()`
- `eizo.mcp.server.serve_mcp()`: FastMCP server, invoked via `eizo mcp`

## CLI conventions

- Global output format: `--output-format [table|json]` (default `table`).
  Do **not** use `--format`; it was removed to avoid collision with the
  `eizo export <format>` subcommand argument.
- Repository path: `--repo <path>` or short `-C <path>` (like `git -C`).
  The old `--path` option was removed.
- Numeric options are validated: `--depth 1..10`, `--limit >=1`,
  `--min-refs >=1`, `--port 1..65535`.
- `architecture` is an alias for `arch` (kept for compatibility).

## Configuration file

- Optional `{repo}/.eizo/config.json` loaded automatically.
- Global `--config <path>` overrides the default location.
- Merge priority: **CLI args > config file > Click defaults**.
- Supported fields (all optional):
  - `"output_format"`: `"table"` or `"json"`.
  - `"no_color"`: `true` or `false`.
  - `"limit"`: integer (`>= 1`), used by `search`/`dead`/`hotspots`.
  - `"full_text"`: boolean, used by `search`.
  - `"depth"`: integer (`1..10`), used by `trace`/`impact`.
  - `"min_refs"`: integer (`>= 1`), used by `hotspots`.
- Invalid JSON prints a warning and falls back to defaults.

## Shell completion

- Supported via Click's built-in completion mechanism.
- `--show-completion [bash|zsh|fish]` prints the completion script.
- `--install-completion [bash|zsh|fish]` prints the same script (redirect to
  your shell config file to install).
- Completion variables use the prefix `_EIZO_COMPLETE`.

## Environment variables

- Supported variables:
  - `EIZO_OUTPUT_FORMAT` — overrides `--output-format` (`table` or `json`).
  - `EIZO_NO_COLOR` — disables colors when set to `1`, `true`, `yes` or `on`.
  - `NO_COLOR` — global standard; also disables colors when set.
  - `EIZO_REPO` — default value for `--repo`/`-C`.
  - `EIZO_CONFIG` — alternative path to the config JSON file.
  - `EIZO_LIMIT` — default for `--limit` in `search`/`dead`/`hotspots`.
  - `EIZO_DEPTH` — default for `--depth` in `trace`/`impact`.
  - `EIZO_MIN_REFS` — default for `--min-refs` in `hotspots`.
  - `EIZO_FULL_TEXT` — default for `--full-text` in `search`.
- Merge priority: **CLI args > env vars > config file > Click defaults**.

## Architecture

```
src/eizo/
├── cli.py          # Click commands (init, search, trace, impact, arch, mcp, status, dead, hotspots, export)
├── indexer.py      # Orchestrator: scan repo → parse files → persist to SQLite (incremental)
├── graph/
│   ├── models.py   # Node, Edge, GraphStats dataclasses
│   ├── schema.py   # SQLite schema (v2), get_db_path(), open_db(), migrate_db()
│   └── store.py    # GraphStore CRUD (upsert, search, FTS5, file_index, trace, stats)
├── parser/
│   ├── base.py     # Abstract BaseParser
│   ├── python.py   # Tree-sitter Python parser
│   └── typescript.py # Tree-sitter TS/JS parser
├── queries/
│   ├── search.py   # search_symbols(), get_symbol_context()
│   ├── trace.py    # trace_call_path() — call graph traversal
│   ├── impact.py   # analyze_impact() — dependency chain
│   ├── analysis.py # find_dead_code(), find_hotspots()
│   └── export.py   # export_dot(), export_mermaid(), export_json()
└── mcp/
    └── server.py   # FastMCP server (7 tools)
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
- Schema v2: `nodes`, `edges`, `file_index` (incremental), `nodes_fts` (FTS5).
- Node IDs: SHA-256(`{file_path}:{name}:{line}`)[:16].
- `file_index` tracks content_hash + mtime per file for incremental indexing.
- `nodes_fts` is a standard FTS5 table (name, docstring, code_snippet) synced
  on every upsert/delete.
- Schema migration: `migrate_db()` upgrades v1 → v2 (adds file_index + nodes_fts).

## Testing

- `store` fixture: `GraphStore(tmp_path)` — SQLite in temp dir.
- `sample_python_file` / `sample_ts_file`: string fixtures for parser tests.
- `sample_python_repo`: creates real dir tree for indexer tests.
- Coverage gate: 70%. `cli.py` and `__main__.py` are untested (0%).
- `asyncio_mode = auto` in pytest config.
- 297 tests total. New test files: `test_incremental.py`, `test_analysis.py`, `test_export.py`.

## Conventions

- `from __future__ import annotations` in every file.
- Type hints on all functions (params + return).
- No `print()` — use `rich.console.Console`.
- Imports: stdlib → third-party → local, alphabetical within groups.
- Ruff: line-length 120, select E/F/I/N/W/UP/B/SIM/ARG/C4.
- Mypy: strict mode, `ignore_missing_imports = true` (tree-sitter, mcp).
- Code in English, docstrings/comments in Portuguese BR.
