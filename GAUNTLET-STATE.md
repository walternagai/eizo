# Gauntlet Loop — Revisão completa do repositório eizō

**Objective**: Revisão completa do repositório (HEAD 7fe9a69, working tree
limpo) — qualidade de código, arquitetura, testes e consistência
código↔docs↔testes, decomposto em 11 componentes avaliados
independentemente por agentes críticos com contexto limpo.

**Metric**: Todo finding citável com evidência concreta (`arquivo:linha`) e
priorizado (P0/P1/P2); verificadores objetivos (ruff, mypy, pytest,
coverage ≥ 70%) rodam limpos no estado atual.

**Boundary**: 1 rodada de crítica por componente; 1 crítico de integração
final. Nenhuma alteração de código — findings viram backlog, não patches.
O relatório final reflete honestamente o que ficou sem revisão.

| Componente | Escopo | Status | Rodada | Último gap crítico (maior gap) |
|---|---|---|---|---|
| docs-e-contrato | AGENTS.md, README.md, docs/api.md, RELEASE_NOTES, CHANGELOG vs código | **fail** | 1 | AGENTS.md diz 719 testes; coleta real = 738; lista de arquivos omite test_public_api.py |
| packaging-config | pyproject.toml, Makefile, .github/, .gitignore | **fail** | 1 | pyproject.toml:53 declara pyyaml>=6.0 como dependência runtime sem um único import yaml |
| cli | src/eizo/cli.py, __main__.py | **fail** | 1 | P0: init/watch ignoram EIZO_REPO (indexam cwd em vez do repo); config/env bypassa validação IntRange (depth 0/limit 0 aceitos) |
| graph-core | src/eizo/graph/{models,schema,store}.py | **fail** | 1 | Escritas multi-statement sem rollback: lock concorrente deixa transação aberta e próximo commit persiste lote parcial com FTS dessincronizado |
| indexer | src/eizo/indexer.py (incremental, purge, ignore) | **fail** | 1 | _should_ignore itera parts do caminho ABSOLUTO: repo em diretório com nome "build"/"dist"/"venv" é filtrado inteiro; detecção de remoção pode apagar o grafo |
| parsers-py-ts | parser/base.py, python.py, typescript.py | **fail** | 1 | Recursão sem limite em _walk_tree/_handle_call: nesting ~500 níveis (input válido!) estoura pilha, arquivo descartado silenciosamente |
| parsers-ngo | parser/{go,rust,java,csharp,php,ruby}.py | **fail** | 1 | impl<T> genéricos em Rust perdem contains+inherits ("Bar<T>" ≠ "Bar" no pre-scan); PHP: use App\{A,B} não emite import; Java: extends qualificado/genérico não gera inherits |
| queries-core | queries/{search,trace,why,impact,analysis,cycles,metrics,diff}.py | **fail** | 1 | docs/api.md promete find_hotspots -> list[Node]; implementação retorna list[dict] — contrato público estável violado sem deprecation cycle |
| export | queries/export.py (dot/mermaid/json/html/svg/png) | **fail** | 1 | export_json não determinístico (SELECT sem ORDER BY + INSERT OR REPLACE reatribui rowid) — dois exports não fazem diff estável |
| mcp-server | mcp/server.py (FastMCP, 8 tools) | **fail** | 1 | src/eizo/mcp/ e parser/ sem __init__.py + find_packages sem namespaces: wheel real perde eizo.mcp e parsers — `eizo mcp` morre com ModuleNotFoundError no install não-editável |
| tests-infra | tests/conftest.py + arquitetura da suíte | **fail** | 1 | test_coverage_gaps.py é caça-coverage declarada: testes ancorados a linhas de código, ~9 sem assert, asserts vacuosamente verdadeiros, vazamento de estado global |
| **integração** | contratos entre componentes (API pública, CLI↔store↔queries↔MCP) | **pass** | 1 | PASS com 5 findings (EIZO_REPO P1 dupla-confirmação; queries dependem de internals _row_to_node; watch cria grafo; config bypass; serialização MCP inconsistente) |

## Log de rodadas

- Rodada 0 — despacho pendente.
- Rodada 1 (2026-09-20) — 11 críticos independentes (Task agents, contexto
  limpo, builder jamais criticou o próprio trabalho) + crítico de integração.
  Resultado: 11 FAIL, 1 PASS. Boundary (1 rodada/componente) atingido — loop
  encerrado conforme declarado. Findings consolidados no relatório final;
  nenhum código alterado (objective da task: revisão, não patch).
- Nota honesta de execução: o crítico de integração rodou em paralelo aos
  componentes, não estritamente após — para uma task de revisão (sem código
  novo a montar), integração = contratos cruzados, e ele executou exatamente
  esse escopo.