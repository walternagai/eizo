# API — Eizō (映像)

Este documento define a **superfície pública estável** do pacote `eizo`,
gerado manualmente (assinaturas + descrição das funções públicas). É a
fonte de verdade da API junto com AGENTS.md — para a deprecation policy,
ver [Deprecation Policy](#deprecation-policy) abaixo.

O projeto é um CLI pequeno sem docs site; a opção escolhida foi um
documento markdown estático (opção C) em vez de MkDocs/Sphinx: cirúrgico,
sem dependência de build nova, sem risco de quebrar `make check`, e
suficiente para a escala atual. Se o projeto crescer para um SDK com docs
públicas hospedadas, a migração natural é MkDocs + mkdocstrings (que
consumiriam estas docstrings já completas).

## Contrato de estabilidade

- **API estável (promessa de compatibilidade)**: o que está em `__all__` de
  `eizo`, `eizo.graph` e `eizo.queries`, mais `eizo.mcp.server.create_server`
  e `eizo.mcp.server.serve_mcp`. Mudanças que quebram esta superfície seguem
  a deprecation policy.
- **CLI estável por contrato de CLI**: `eizo.cli` é estável quanto a
  comandos/opções, não quanto a imports Python (módulo interno).
- **Internos (podem mudar sem aviso)**: `eizo.graph.schema`,
  `eizo.graph.store` (usar `GraphStore` via re-export), `eizo.parser.*`,
  `eizo.indexer` (usar `index_repository` via re-export), `eizo.static`,
  `eizo.__main__` e qualquer função com prefixo `_`.

## `eizo` (pacote raiz)

Re-exports de `eizo.graph`, `eizo.indexer` e `eizo.queries`:

| Símbolo | Tipo | Origem |
|---------|------|--------|
| `GraphStore` | class | `eizo.graph.store` |
| `Node` | dataclass | `eizo.graph.models` |
| `Edge` | dataclass | `eizo.graph.models` |
| `GraphStats` | dataclass | `eizo.graph.models` |
| `DEFINITION_KINDS` | frozenset | `eizo.graph.models` |
| `index_repository` | function | `eizo.indexer` |
| `search_symbols`, `get_symbol_context` | function | `eizo.queries.search` |
| `trace_call_path` | function | `eizo.queries.trace` |
| `find_dependency_path` | function | `eizo.queries.why` |
| `analyze_impact` | function | `eizo.queries.impact` |
| `find_dead_code`, `find_hotspots` | function | `eizo.queries.analysis` |
| `find_import_cycles` | function | `eizo.queries.cycles` |
| `compute_symbol_metrics` | function | `eizo.queries.metrics` |
| `diff_against_ref`, `diff_between_refs` | function | `eizo.queries.diff` |
| `export_dot`, `export_mermaid`, `export_json`, `export_html`, `export_svg`, `export_png`, `export_architecture_mermaid` | function | `eizo.queries.export` |
| `__version__` | str | — |

## `eizo.graph`

```python
class GraphStore(path: Path | None = None)
```

CRUD no SQLite do grafo de conhecimento. Métodos públicos (estáveis):

- `conn` — conexão SQLite (aberta sob demanda).
- `close()` — fecha a conexão (idempotente).
- `upsert_node(node)`, `upsert_nodes(nodes)` — persistência em lote com
  sincronização FTS5 por rowid determinístico.
- `get_node(node_id)`, `get_nodes_by_name(name, kind=None)`,
  `get_nodes_by_file(file_path)` — leitura de nós.
- `search_nodes(query, kind=None, language=None, limit=50)` — busca por
  nome (LIKE), priorizando match exato e definições.
- `search_nodes_fts(query, kind=None, language=None, limit=50)` — busca
  full-text (FTS5) ranqueada por relevância.
- `delete_nodes_by_file(file_path)`, `clear_all()` — remoção.
- `get_file_index_entry(file_path)`, `upsert_file_index(...)`,
  `get_indexed_files()`, `delete_file_index(file_path)`,
  `is_file_unchanged(file_path, content_hash)` — índice incremental.
- `upsert_edge(edge)`, `upsert_edges(edges)`,
  `get_outgoing_edges(node_id, kind=None)`,
  `get_incoming_edges(node_id, kind=None)` — arestas.
- `resolve_call_to_definition(call_node)` — resolve call site → definição.
- `get_real_references(node_id, node_name)` — referências reais
  (calls/imports/inherits), deduplicadas.
- `get_file_import_graph()` — grafo de imports em nível de arquivo
  (aproximação best-effort).
- `get_stats()` — estatísticas do grafo.

Dataclasses: `Node`, `Edge`, `GraphStats`; constante `DEFINITION_KINDS`.

## `eizo.queries`

```python
search_symbols(store, query, kind=None, language=None, limit=50, full_text=False) -> list[Node]
get_symbol_context(store, node_id, depth=1) -> dict[str, Any]
trace_call_path(store, symbol_name, direction="both", max_depth=5) -> dict[str, Any]
find_dependency_path(store, symbol_a, symbol_b, max_depth=10) -> dict[str, Any]
analyze_impact(store, symbol_name, max_depth=3) -> dict[str, Any]
find_dead_code(store, entrypoints=None, limit=100) -> list[Node]
find_hotspots(store, limit=20, min_references=2) -> list[Node]
find_import_cycles(store) -> list[dict[str, Any]]
compute_symbol_metrics(store, symbol_name) -> list[dict[str, Any]]
diff_against_ref(repo_path, ref) -> dict[str, Any]
diff_between_refs(repo_path, ref1, ref2) -> dict[str, Any]
export_dot(store, kind=None, language=None, limit=None, edge_kinds=None) -> str
export_mermaid(store, kind=None, language=None, limit=None, edge_kinds=None, diagram_type="flowchart") -> str
export_json(store, kind=None, language=None, limit=None, edge_kinds=None) -> str
export_html(store, kind=None, language=None, limit=None, edge_kinds=None) -> str
export_svg(store, kind=None, language=None, limit=None, edge_kinds=None) -> bytes
export_png(store, kind=None, language=None, limit=None, edge_kinds=None) -> bytes
export_architecture_mermaid(store) -> str
```

`export_json` retorna um objeto JSON com duas chaves: `nodes` e `edges`. Cada
nó contém `id`, `name`, `kind`, `file_path`, `language`, `line_start`,
`line_end` e `docstring`; cada aresta contém `source_id`, `target_id` e
`kind`.

> `export_svg`/`export_png` renderizam via binário `dot` (graphviz) e
> levantam `RuntimeError` se ele não estiver instalado. Graphviz é
> dependência opcional de sistema — ver README, seção Requisitos.

## `eizo.mcp.server`

Funções públicas estáveis: `create_server` e `serve_mcp`.

```python
create_server(store, port=8765) -> FastMCP
serve_mcp(store, port=8765, transport="sse") -> None
```

## Deprecation Policy

A partir do Sprint 9 (rumo a 1.0.0), mudanças que quebrem a API estável
(ver [Contrato de estabilidade](#contrato-de-estabilidade)) seguem um ciclo
de deprecation de **duas versões**:

1. **Versão N**: o símbolo continua funcionando, mas emite um
   `DeprecationWarning` (via `warnings.warn(..., DeprecationWarning,
   stacklevel=2)`) orientando para o substituto, e a mudança é registrada
   no CHANGELOG.
2. **Versão N+1**: o símbolo é removido. A remoção é registrada no
   CHANGELOG como breaking change.

Exceções (podem quebrar sem ciclo): correções de segurança, correções de
bugs que tornam o comportamento atual indefinido, e mudanças em símbolos
internos (fora de `__all__`). A superfície CLI (comandos/opções) segue o
mesmo ciclo de duas versões quando um comando/opção é removido ou
renomeado.
