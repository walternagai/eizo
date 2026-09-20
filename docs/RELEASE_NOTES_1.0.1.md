# Eizō 1.0.1 — Release Notes

Eizō 1.0.1 é a primeira release **publicada no PyPI** e concentra correções
de robustez identificadas por uma revisão completa do codebase (revisão
gauntlet com 11 componentes auditados por críticos independentes). Nenhuma
breaking change — a API pública estável de `eizo`, `eizo.graph`,
`eizo.queries` e `eizo.mcp.server` permanece intacta.

## Destaques

### CLI

- `EIZO_REPO` agora é respeitado por `eizo init` e `eizo watch` (antes,
  indexavam/observavam o diretório atual ignorando a variável).
- Valores numéricos de `EIZO_*` ou de `.eizo/config.json` são validados nas
  mesmas faixas do CLI (`depth` 1..10, `limit`/`min_refs` >= 1); fora da
  faixa, aviso + default em vez de aplicar silenciosamente.
- `eizo watch` exige repositório já indexado: falha com
  `ClickException` ("não indexado") em vez de criar o grafo silenciosamente
  — somente `init` cria grafo.

### Grafo (SQLite)

- `upsert_node()`/`upsert_nodes()` usam upsert real (`ON CONFLICT DO UPDATE`)
  em vez de `INSERT OR REPLACE`: o REPLACE disparava o FK
  `ON DELETE CASCADE` e apagava silenciosamente as arestas incidentes ao
  re-upsertar um nó.
- Escritas multi-statement (`upsert_nodes`, `delete_nodes_by_file`,
  `clear_all`) fazem rollback em exceção — um lock concorrente não deixa
  mais transação aberta nem persiste lote parcial com FTS dessincronizado.
- `GraphStore` cacheia leituras de resolução (nodes por nome, stubs),
  invalidando em toda escrita: `find_hotspots`/`find_dead_code` fazem
  ~3.2× menos lookups de nome em repos com definições homônimas.

### Indexação

- `_should_ignore` compara apenas partes do caminho **relativas à raiz** —
  um repo clonado sob `.../build/` ou `.../venv/` não é mais filtrado
  inteiro (nem apagado pela detecção de remoção).

### Parsers (8 linguagens)

- Guard de profundidade da AST nos 8 parsers (`MAX_AST_DEPTH`, constante
  única em `parser/base.py`): aninhamento profundo de input válido (bundles
  minificados) vira **parse parcial** em vez de estourar a pilha e descartar
  o arquivo silenciosamente.
- Pre-scans de Go/Rust percorrem a AST iterativamente (rodavam recursivamente
  antes do guard).

### Export

- Export do grafo é **determinístico**: nós ordenados por
  (file_path, name, id) e arestas por (source, target, kind) — dois exports
  do mesmo grafo fazem diff estável.
- Labels de DOT escapam `"`, `\` e quebras de linha; comentários `%%` do
  classDiagram Mermaid sanitizam nomes.

### Empacotamento

- `eizo.parser` e `eizo.mcp` agora são incluídos no wheel — em instalações
  não-editáveis de versões anteriores, `eizo mcp` morria com
  `ModuleNotFoundError`.
- Dependências mortas removidas (`pyyaml`, `pytest-asyncio`, `pre-commit`).

## Instalação

```bash
pip install eizo
```

Graphviz é opcional (só para `eizo export svg`/`export png`).

## Verificação

- ruff/mypy (strict) limpos; 774 testes passando; coverage 95.6%.
- Wheel testado em venv limpo: indexação, search, trace, export e
  `eizo mcp` (import de `create_server`) funcionam fora do venv de dev.