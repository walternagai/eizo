# Changelog

Todas as mudanças notáveis do Eizō serão documentadas neste arquivo.

O formato é baseado no [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Adicionado

- **API pública estável (B14)**: `__all__` explícito em `eizo`, `eizo.graph` e `eizo.queries`; contrato de estabilidade e deprecation policy documentados em `AGENTS.md`, `README.md` e `docs/api.md`
- **Docs de API (B15)**: `docs/api.md` com assinaturas e descrição de toda a superfície pública; docstrings completas (Args/Returns) em todos os módulos públicos
- **`eizo diff <ref1>..<ref2>` (B13)**: diff de símbolos entre dois refs git, além do diff working-tree-vs-ref já existente (`diff_between_refs` em `eizo.queries.diff`)
- Chamadas dentro de macros Rust (`println!`, `format!`, `vec!`, macros custom) agora são capturadas — re-parse do argumento `token_tree` como expressões (B8)
- Fuzz tests determinísticos dos parsers (seed fixa) — nenhum input malformado pode crashar o parse (B11)
- Benchmark de indexação em escala (`benchmarks/benchmark_index.py`) com resultados documentados em `benchmarks/RESULTS.md` (B12)
- Actions do CI atualizadas para `actions/checkout@v7` e `actions/setup-python@v7` (Node 20 deprecado) (B16)

### Corrigido

- Teto de dependência `mcp<2.0`: mcp 2.0 removeu `mcp.server.fastmcp` (quebra o import) e deixou o decorator `@mcp.tool()` sem tipagem (quebra `mypy --strict` com `untyped-decorator`)
- Teste `test_cli_merge_config_no_command_values` dependia do CWD: falhava em ambiente limpo (CI) sem `.eizo/graph.db`; agora usa `monkeypatch.chdir` num repo indexado vazio

## [0.2.0] - 2026-08-01

### Adicionado

- Parsers Tree-sitter para **Go**, **Rust** e **Java** (além de Python e TypeScript/JavaScript)
- Comando `eizo watch` — reindexação contínua por polling enquanto houver mudanças
- Comando `eizo diff <ref>` — compara símbolos do working tree contra um ref git
- Comando `eizo why <a> <b>` — caminho mais curto de dependência entre dois símbolos
- Comando `eizo cycles` — detecção de ciclos de import (Tarjan SCC)
- Comando `eizo metrics <symbol>` — fan-in, fan-out e LOC por símbolo
- Suporte a `.gitignore` e `.eizoignore` na raiz do repositório indexado
- Detecção de arquivos **removidos** na indexação incremental (sem flag)

### Corrigido

- Colisão de `node_id` em símbolos homônimos (SHA-256 inclui coluna)

### Alterado

- Schema SQLite **v3**: índice FTS ancorado em rowid determinístico (`fts_rowid`)
- Piso de dependência elevado para `mcp>=1.28`

### Documentação

- README e AGENTS.md atualizados com as 7 features novas (Tier 1 + Tier 2)

## [0.1.0] - 2026-07-13

### Adicionado

- Release inicial do Eizō (映像) — Codebase Knowledge Graph CLI
- CLI com 16 comandos (Click + Rich)
- Parsers Tree-sitter para **Python** e **TypeScript/JavaScript**
- Indexação **incremental** (cache por hash SHA-256 + mtime)
- Detecção de **código morto** (`eizo dead`)
- **Hotspots** — símbolos mais referenciados (`eizo hotspots`)
- Export do grafo em **DOT**, **Mermaid**, **JSON** e **HTML 3D** (vis-network)
- Servidor **MCP** (8 ferramentas) com transporte SSE e stdio
- Busca textual e full-text (FTS5)
- Call graph (`eizo trace`), análise de impacto (`eizo impact`), visão arquitetural (`eizo arch`)
