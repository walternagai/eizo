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

- `eizo` CLI: `eizo.cli:main` (Click group, 16 commands)
- `python -m eizo`: `eizo/__main__.py` → `cli.main()`
- `eizo.mcp.server.serve_mcp()`: FastMCP server, invoked via `eizo mcp`

## CLI conventions

- Global output format: `--output-format [table|json]` (default `table`).
  Do **not** use `--format`; it was removed to avoid collision with the
  `eizo export <format>` subcommand argument.
- Repository path: `--repo <path>` or short `-C <path>` (like `git -C`).
  The old `--path` option was removed.
- The `init` command accepts either a positional `[PATH]` or `--repo`/`-C`.
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

## Color output

- `--no-color` disables colors (useful for CI or piping).
- `--color` forces colors even when output is redirected.
- `NO_COLOR` / `EIZO_NO_COLOR` disables colors by default.
- Merge priority: `--color` > `--no-color` > env vars > config file.

## Logging and verbosity

- Global options:
  - `-v` / `--verbose` — sets logger `eizo` to INFO.
  - `-vv` — sets logger `eizo` to DEBUG.
  - `--quiet` — only ERROR messages are emitted (overrides `-v`/`-vv`).
- Default level is WARNING.
- Format: `LEVEL: message`.

## Incremental indexing

- `eizo init` syncs the graph with disk on every run — created, modified **and
  deleted** files. No flag needed.
- Deletion detection compares `file_index` against *every* file the walk found,
  not against the reindex list (which excludes unchanged files). Getting this
  wrong would purge unchanged files.
- The purge is scoped to the root being walked: entries outside it are left
  alone, since the same store may have indexed another tree.
- It runs before the "no parseable files" early return — emptying a repo must
  still empty the graph.
- `--force` only bypasses the hash cache (reparses everything); it is *not* what
  removes orphans. `--rebuild` wipes the graph and starts over.
- A `call` node referencing a symbol whose definition file was deleted stays:
  the calling file still exists and still contains that reference.

## Ignore patterns

- `.gitignore` and `.eizoignore` at the **root of the indexed repo** are
  combined (via `pathspec`, gitignore syntax) and applied during the walk —
  both directory pruning and file filtering. Nested `.gitignore` files
  (subdirectories) are not read, unlike real git.
- `.eizoignore` is for excluding from the graph something git *does* track —
  e.g. a vendored `.min.js` shipped as package data. It doesn't affect what
  git tracks, only what eizo indexes.
- Directory-only patterns (`dist/`) only match `pathspec.match_file()` when
  the tested path also ends in `/` — plain `dirname` without the trailing
  slash silently never matches a `dirname/` pattern.

## Watch mode

- `eizo watch` polls (`time.sleep(interval)`, default 2s) and reuses
  `index_repository`'s incremental logic — no filesystem-event dependency
  (no `watchdog`).
- Change detection for the printed summary line compares `get_indexed_files()`
  and `get_stats()` before/after each tick — an edit that doesn't change node
  count (e.g. only a function body, same symbol count) produces no summary
  line. This is a stated tradeoff, not a bug: recomputing a hash-based diff
  purely for the summary would add an extra file read per tick.

## Dry-run

- `eizo init --dry-run` lists files that would be indexed without persisting
  to the SQLite graph.
- Output can be table (default) or JSON via `--output-format json`.

## Architecture

```
src/eizo/
├── cli.py          # Click commands (init, watch, diff, search, trace, why, impact,
│                    #   arch, mcp, status, dead, cycles, hotspots, metrics, export)
├── indexer.py      # Orchestrator: scan repo → parse files → persist to SQLite (incremental)
├── graph/
│   ├── models.py   # Node, Edge, GraphStats dataclasses
│   ├── schema.py   # SQLite schema (v3), get_db_path(), open_db(), migrate_db(), fts_rowid()
│   └── store.py    # GraphStore CRUD (upsert, search, FTS5, file_index, trace, stats,
│                    #   get_file_import_graph, get_indexed_files)
├── parser/
│   ├── base.py     # Abstract BaseParser
│   ├── python.py   # Tree-sitter Python parser
│   ├── typescript.py # Tree-sitter TS/JS parser
│   ├── go.py       # Tree-sitter Go parser
│   └── rust.py     # Tree-sitter Rust parser
├── queries/
│   ├── search.py   # search_symbols(), get_symbol_context()
│   ├── trace.py    # trace_call_path() — call graph traversal
│   ├── why.py      # find_dependency_path() — shortest path between two symbols
│   ├── impact.py   # analyze_impact() — dependency chain
│   ├── analysis.py # find_dead_code(), find_hotspots(), real_referrers()
│   ├── cycles.py   # find_import_cycles() — Tarjan SCC over the file-level import graph
│   ├── metrics.py  # compute_symbol_metrics() — fan-in/fan-out/LOC
│   ├── diff.py     # diff_against_ref() — symbol-level diff vs a git ref
│   └── export.py   # export_dot(), export_mermaid(), export_json()
    └── mcp/
    │       └── server.py   # FastMCP server (8 tools)
```

## Tree-sitter quirks

- `tree-sitter>=0.23`: `language()` returns a **PyCapsule**, not a `Language` object.
  Must wrap: `Language(capsule)`.
- Python inheritance field is `superclasses` (not `bases`).
- TypeScript inheritance: `class_heritage` → `extends_clause` → `identifier`.
- Docstring extraction: remove quote chars from the `string` node manually.
- Go has no classes: `struct_type`/`interface_type` from `type_spec` map to
  `kind="class"`; embedded (unnamed) struct fields map to `inherits`, since
  that's Go's closest analogue to inheritance (composition).
- Go methods (`func (r T) M()`) are **not** AST-nested inside their receiver
  type's declaration, unlike Python/TS methods inside a class body — the
  receiver type can even be declared later in the same file. `go.py`
  pre-scans all `type_spec` positions before the main walk so a method's
  `contains` edge can be resolved regardless of declaration order.
- Rust has no classes: `struct_item`/`trait_item`/`enum_item` map to
  `kind="class"`. Methods live in a separate `impl Type {...}` block (or
  `impl Trait for Type {...}`), same "not AST-nested, order-independent"
  problem as Go — `rust.py` reuses the same pre-scan-positions trick.
  `impl Trait for Type` becomes an `inherits` edge (closest Rust analogue to
  subclassing); `impl Type` alone doesn't.
- **Known limitation**: `rust.py` can't see calls made *inside* a macro
  invocation (`println!(...)`, `format!(...)`, `vec![...]`, etc.).
  tree-sitter-rust doesn't parse a macro's arguments as expressions — it's
  an opaque `token_tree` of raw tokens, since macro expansion rules are
  arbitrary and the grammar can't interpret them without expanding the
  macro. `d.speak()` inside `println!("{}", d.speak())` never becomes a
  `call_expression`, so that call is silently absent from the graph.

## MCP quirks

- Uses `FastMCP` (not low-level `Server`). Tools registered via `@mcp.tool()` decorator.
- Port set in constructor: `FastMCP("eizo", port=8765)`, not as attribute.
- Run with `mcp.run(transport="sse")`.

## SQLite

- DB stored at `{repo}/.eizo/graph.db`. WAL mode + foreign keys ON.
- Schema v3: `nodes`, `edges`, `file_index` (incremental), `nodes_fts` (FTS5).
- Node IDs: SHA-256(`{file_path}:{name}:{line}`)[:16].
- `file_index` tracks content_hash + mtime per file for incremental indexing.
- `nodes_fts` is a standard FTS5 table (name, docstring, code_snippet) synced
  on every upsert/delete.
- **FTS rows are anchored to a deterministic rowid** via `schema.fts_rowid()`.
  `node_id` is UNINDEXED, so deleting by it scans the whole index — that made
  reindexing quadratic in repo size. Always delete/insert FTS rows *by rowid*.
- `upsert_nodes()` collapses duplicate ids within a batch (last one wins,
  matching `INSERT OR REPLACE`). Minified files put every symbol on one line, so
  `file:name:line` collides by the thousands inside a single file.
- Schema migration: `migrate_db()` upgrades v1 → v2 (adds file_index +
  nodes_fts) and v2 → v3 (rebuilds nodes_fts with deterministic rowids).

## Testing

- `store` fixture: `GraphStore(tmp_path)` — SQLite in temp dir. `indexed_empty_repo`
  fixture: a repo whose `.eizo/graph.db` exists but has no symbols — distinct
  from a bare `tmp_path`, which query commands reject as *not indexed*.
- `sample_python_file` / `sample_ts_file`: string fixtures for parser tests.
- Go has no equivalent `sample_go_file` fixture; `test_parser_go.py` inlines
  sources directly (matches the granularity of the other parser test files).
- `sample_python_repo`: creates real dir tree for indexer tests.
- Scalability regression is locked by `TestIndexingScales`, which counts SQLite
  VM steps via `set_progress_handler` rather than wall clock (deterministic).
- `watch`'s infinite loop is tested by mocking `eizo.cli.time.sleep` with a
  `side_effect` that mutates files then raises `KeyboardInterrupt` — drives a
  bounded number of iterations through `CliRunner` without hanging the suite.
- Coverage gate: 70%.
- `cli.py`: 99% coverage; `__main__.py`: 100% coverage.
- `asyncio_mode = auto` in pytest config.
- 581 tests total. Test files include: `test_cli.py`, `test_main.py`, `test_indexer.py`,
  `test_indexer_extended.py`, `test_incremental.py`, `test_analysis.py`, `test_export.py`,
  `test_export_html.py`, `test_queries_extended.py`, `test_store_extended.py`,
  `test_parser_python_extended.py`, `test_parser_typescript_extended.py`,
  `test_parser_go.py`, `test_parser_go_extended.py`,
  `test_parser_rust.py`, `test_parser_rust_extended.py`,
  `test_mcp_server.py`, `test_coverage_gaps.py`, `test_queries_cycles.py`,
  `test_queries_metrics.py`, `test_queries_why.py`, `test_queries_diff.py`,
  `test_cli_cycles.py`, `test_cli_metrics.py`, `test_cli_why.py`, `test_cli_diff.py`.

## Error handling

- Query commands open the graph via `cli._open_store()`, never `GraphStore()`
  directly. Only `init` may create a graph.
- Repo without `.eizo/graph.db` → `ClickException` ("não indexado", exit 1), and
  nothing is written to disk. Previously this silently created an empty graph and
  reported "no results", indistinguishable from a genuine empty match.
- Corrupted DB → `ClickException` suggesting `eizo init --rebuild`, instead of a
  raw `sqlite3.DatabaseError` traceback.
- Indexed but empty graph stays a normal case: "Grafo vazio", exit 0.

## Dependencies

- `mcp>=1.28` is a floor, not cosmetic: earlier versions build tool output
  schemas in a way that breaks with `pydantic>=2.11`, which `mcp` itself now
  requires. A venv with `mcp>=1.28` and `pydantic<2.11` fails at
  `create_server()` with `PydanticUserError`.
- `pathspec>=1.1` — gitignore-syntax matcher for `.gitignore`/`.eizoignore`
  support in the indexer. Uses the `"gitignore"` pattern factory name in
  `PathSpec.from_lines()`, not the older `"gitwildmatch"` alias (deprecated,
  emits a warning).
- `tree-sitter-go>=0.23` — Go parser. Exposes `language()` returning a
  PyCapsule, same pattern as `tree-sitter-python`/`tree-sitter-typescript`.
- `tree-sitter-rust>=0.23` — Rust parser. Same PyCapsule pattern.

## Node identity

- `Node.id` = SHA-256(`{file_path}:{name}:{line}:{column}`)[:16] — column was
  added because line alone collides in minified/generated files (thousands of
  symbols on one physical line). `GraphStore.upsert_nodes()` still collapses
  same-id duplicates within a batch (last write wins), since column disambiguates
  *most* but not all cases (e.g. two homonymous methods that happen to start at
  the exact same offset across different generated blocks).
- Call-site position (`kind='call'` nodes) is taken from the method-name token
  (`attribute`/`member_expression`'s `property` field), **not** from the
  enclosing `attribute`/`member_expression` node itself — that node's own
  `start_point` is the position of the *object*, not the method name. Get this
  wrong and `x.f().f()` (same method name called twice in one chain) collides:
  both calls' enclosing nodes start at `x`.

## Conventions

- `from __future__ import annotations` in every file.
- Type hints on all functions (params + return).
- No `print()` — use `rich.console.Console`.
- Imports: stdlib → third-party → local, alphabetical within groups.
- Ruff: line-length 120, select E/F/I/N/W/UP/B/SIM/ARG/C4.
- Mypy: strict mode, `ignore_missing_imports = true` (tree-sitter, mcp).
- Code in English, docstrings/comments in Portuguese BR.
