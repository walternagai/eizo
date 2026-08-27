# TASK-001 — Corrigir sincronização FTS em `upsert_node()`

- **Status:** Concluída
- **Prioridade:** P0
- **Tipo:** Bug de API pública
- **Release alvo:** 1.0.1
- **Dependências:** Nenhuma

## Problema

`GraphStore.upsert_nodes()` atualiza o índice `nodes_fts`, mas
`GraphStore.upsert_node()` grava apenas a tabela `nodes`. A API documentada em
`docs/api.md` promete sincronização FTS para os dois métodos.

Reprodução observada:

```python
store.upsert_node(Node(id="n", name="fts_unique_term", kind="function",
                       file_path="a.py", language="python"))
store.search_nodes_fts("fts_unique_term")  # retorna []
```

## Escopo

- Fazer o caminho unitário e o caminho em lote compartilharem a mesma lógica de
  persistência e sincronização FTS5.
- Preservar o `rowid` determinístico definido por `fts_rowid()`.
- Garantir que uma atualização do mesmo `id` substitua o conteúdo antigo no FTS.
- Adicionar regressões cobrindo inserção, atualização, busca e remoção por
  arquivo.

## Critérios de aceite

- [x] `upsert_node()` torna o nó imediatamente pesquisável por nome,
      docstring e `code_snippet` via `search_nodes_fts()`.
- [x] Atualizar o mesmo nó não deixa conteúdo antigo nem linhas FTS órfãs.
- [x] `delete_nodes_by_file()` remove também a entrada FTS criada pelo caminho
      unitário.
- [x] O comportamento já coberto de `upsert_nodes()` permanece inalterado,
      inclusive para IDs duplicados no mesmo lote.
- [x] A documentação da API continua refletindo o comportamento implementado.

## Verificação

```bash
python -m ruff check src/eizo/ tests/
python -m pytest tests/test_store.py tests/test_store_extended.py -q
python -m pytest --cov=src/eizo --cov-fail-under=70 -q
```

## Não escopo

Alterar a sintaxe de consultas FTS5, a estratégia de ranking ou o schema do
banco.
