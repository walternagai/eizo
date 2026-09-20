# Changelog

Todas as mudanças notáveis do Eizō serão documentadas neste arquivo.

O formato é baseado no [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Corrigido

- `GraphStore.upsert_node()` agora sincroniza o índice FTS5, assim como
  `upsert_nodes()`.
- `EIZO_REPO` agora é respeitado por `eizo init` e `eizo watch` (antes,
  indexavam/observavam o diretório atual ignorando a variável).
- Valores de `depth`/`limit`/`min_refs` vindos de `EIZO_*` ou de
  `.eizo/config.json` agora são validados nas mesmas faixas do CLI
  (`depth` 1..10, `limit`/`min_refs` >= 1); fora da faixa, emite aviso e
  usa o default em vez de aplicar o valor silenciosamente.
- `eizo.parser` e `eizo.mcp` agora são incluídos no wheel — antes,
  `find_packages` os omitia (sem `__init__.py`) e instalações não-editáveis
  perdiam todos os parsers e o comando `eizo mcp`.
- Escritas multi-statement do `GraphStore` (`upsert_nodes`,
  `delete_nodes_by_file`, `clear_all`) agora fazem rollback em exceção: um
  lock concorrente no meio da sequência não deixa mais transação aberta
  nem persiste lote parcial com FTS dessincronizado.
- `_should_ignore` do indexer compara apenas as partes do caminho
  RELATIVAS à raiz do repo — um repositório clonado sob um diretório com
  nome "build"/"venv"/"dist" não é mais filtrado inteiro (nem apagado do
  grafo pela detecção de remoção).
- Parsers Python e TypeScript toleram aninhamento profundo de input válido
  (bundles minificados): travessia da AST guarda profundidade e RecursionError
  vira parse parcial com aviso, em vez de descartar o arquivo inteiro.
- Guard de profundidade estendido aos 6 parsers restantes (Go, Rust, Java,
  C#, PHP, Ruby), com a constante única `MAX_AST_DEPTH` em `parser/base.py`;
  os pre-scans de Go/Rust passam a percorrer a AST iterativamente (rodavam
  recursivamente antes do guard).
- Export do grafo é determinístico: `_fetch_nodes`/`_fetch_edges_for_nodes`
  ordenam por chaves estáveis (file_path/name/id e source/target/kind) —
  dois exports do mesmo grafo fazem diff estável mesmo depois de re-indexar
  (INSERT OR REPLACE reatribuía rowids e embaralhava a ordem).
- Labels de DOT escapam `"`, `\` e quebras de linha (símbolo com aspas no
  nome não produz mais DOT inválido — export_svg/export_png herdam a
  correção via export_dot); nomes com newline não quebram mais os comentários
  `%%` do classDiagram Mermaid.
- `find_hotspots()` retorna `list[Node]` conforme o contrato de docs/api.md
  (a contagem fica em `metadata["reference_count"]` do nó); antes retornava
  `list[dict]`, divergindo da API estável documentada.

### Alterado

- Metadata de distribuição, matriz de Python, licença e documentação de
  instalação alinhados com o status de API estável do projeto.
- Dependências removidas por não serem usadas: `pyyaml` (runtime),
  `pytest-asyncio` + `asyncio_mode` (nenhum teste async) e `pre-commit`
  (sem `.pre-commit-config.yaml`).

## [1.0.0] - 2026-08-10

### Adicionado

- **API pública estável (B14)**: `__all__` explícito em `eizo`, `eizo.graph` e `eizo.queries`; contrato de estabilidade e deprecation policy documentados em `AGENTS.md`, `README.md` e `docs/api.md`
- **Docs de API (B15)**: `docs/api.md` com assinaturas e descrição de toda a superfície pública; docstrings completas (Args/Returns) em todos os módulos públicos
- **`eizo diff <ref1>..<ref2>` (B13)**: diff de símbolos entre dois refs git, além do diff working-tree-vs-ref já existente (`diff_between_refs` em `eizo.queries.diff`)
- **Export SVG/PNG (B10)**: `eizo export svg` e `eizo export png` renderizam o grafo via graphviz (`dot -Tsvg`/`-Tpng`); graphviz é dependência opcional de sistema, não Python
- Parsers Tree-sitter para **C#**, **PHP** e **Ruby** — 8 linguagens no total (Python, TypeScript/JavaScript, Go, Rust, Java, C#, PHP, Ruby)
- Chamadas dentro de macros Rust (`println!`, `format!`, `vec!`, macros custom) agora são capturadas — re-parse do argumento `token_tree` como expressões (B8)
- Fuzz tests determinísticos dos parsers (seed fixa) — nenhum input malformado pode crashar o parse (B11)
- Benchmark de indexação em escala (`benchmarks/benchmark_index.py`) com resultados documentados em `benchmarks/RESULTS.md` (B12)
- Actions do CI atualizadas para `actions/checkout@v7` e `actions/setup-python@v7` (Node 20 deprecado) (B16)
- CI multi-OS: suíte completa (lint + typecheck + testes + coverage) em `ubuntu-latest`, `macos-latest` e `windows-latest`, com Python 3.10/3.11/3.12

### Corrigido

- Portabilidade Windows: `_display_path` normaliza separadores (`\` → `/`) e o teste de `get_db_path` compara com `Path` em vez de string hardcoded — 2 testes falhavam no CI Windows
- Performance: `_fetch_edges_for_nodes` montava um único `IN` com N placeholders — em grafos grandes (10k+ nós) estourava o limite de variáveis do SQLite ou degradava para scan lento (export travava). Agora quebra em batches de 500 ids
- Teto de dependência `mcp<2.0`: mcp 2.0 removeu `mcp.server.fastmcp` (quebra o import) e deixou o decorator `@mcp.tool()` sem tipagem (quebra `mypy --strict` com `untyped-decorator`)
- Teste `test_cli_merge_config_no_command_values` dependia do CWD: falhava em ambiente limpo (CI) sem `.eizo/graph.db`; agora usa `monkeypatch.chdir` num repo indexado vazio

### Alterado

- Versão promovida de `0.3.0` para **1.0.0** — API pública estável desde o Sprint 9, sem breaking changes nesta release
- `eizo export` aceita os formatos `svg` e `png` além de `dot`, `mermaid`, `json` e `html`

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
