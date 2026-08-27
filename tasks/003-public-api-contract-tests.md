# TASK-003 — Criar testes de contrato da API pública

- **Status:** Backlog
- **Prioridade:** P1
- **Tipo:** Qualidade / compatibilidade
- **Release alvo:** 1.0.1
- **Dependências:** Nenhuma

## Problema

`eizo`, `eizo.graph` e `eizo.queries` definem `__all__` e
`docs/api.md` declara uma superfície estável, mas não há testes que falhem
quando um re-export público desaparece ou é renomeado. A documentação da API é
mantida manualmente.

## Escopo

- Criar uma suíte de contrato, preferencialmente em
  `tests/test_public_api.py`.
- Verificar que cada nome de `__all__` existe e pode ser importado pelo módulo
  público correto.
- Verificar que os re-exports principais do pacote raiz continuam disponíveis:
  `GraphStore`, modelos, `index_repository` e funções de query/export.
- Verificar os nomes e opções essenciais da CLI estável, incluindo o alias
  `architecture`.
- Verificar formatos JSON representativos para evitar remoções acidentais de
  campos documentados.
- Reaproveitar os testes MCP existentes e adicionar apenas lacunas de contrato
  que ainda não estejam cobertas.

## Critérios de aceite

- [ ] Remover ou renomear um símbolo listado em `__all__` faz a suíte falhar.
- [ ] Todos os exports documentados em `docs/api.md` são exercitados por pelo
      menos um teste de importação ou comportamento.
- [ ] Os 16 comandos CLI e o alias `architecture` ficam protegidos por teste.
- [ ] Os formatos JSON testados mantêm seus campos públicos documentados.
- [ ] Os testes não congelam módulos internos, funções privadas ou detalhes de
      implementação não prometidos.
- [ ] A cobertura permanece acima de 70%.

## Verificação

```bash
python -m pytest tests/test_public_api.py tests/test_cli.py tests/test_mcp_server.py -q
python -m ruff check src/eizo/ tests/
python -m pytest --cov=src/eizo --cov-fail-under=70 -q
```

## Não escopo

Alterar a superfície pública ou introduzir uma ferramenta de geração de
documentação. Se um conflito entre código, teste e `docs/api.md` for
encontrado, registrar a decisão antes de editar o contrato.
