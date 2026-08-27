# Backlog técnico

Tasks derivadas da revisão do codebase realizada em 2026-08-27. A ordem
prioriza correções que afetam o contrato público antes de melhorias de
robustez e cobertura.

| ID | Prioridade | Release alvo | Tema | Status |
|---|---|---|---|---|
| [TASK-001](001-fix-fts-upsert-node.md) | P0 | 1.0.1 | Corrigir sincronização FTS no `upsert_node()` | Backlog |
| [TASK-002](002-release-metadata-packaging.md) | P1 | 1.0.1 | Alinhar metadata, licença e empacotamento | Backlog |
| [TASK-003](003-public-api-contract-tests.md) | P1 | 1.0.1 | Criar testes de contrato da API pública | Backlog |
| [TASK-004](004-parser-fuzz-eight-languages.md) | P2 | 1.1.0 | Expandir fuzzing para os oito parsers | Backlog |

## Sequenciamento

1. Executar a `TASK-001`, pois ela corrige um comportamento documentado da
   API pública.
2. Executar `TASK-002` e `TASK-003` antes de publicar a próxima release
   corretiva.
3. Executar `TASK-004` antes de ampliar novamente a superfície funcional.

Cada task deve ser fechada somente após os critérios de aceite e as
verificações listadas no próprio arquivo serem executados.
