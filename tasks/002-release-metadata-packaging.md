# TASK-002 — Alinhar metadata de release e empacotamento

- **Status:** Backlog
- **Prioridade:** P1
- **Tipo:** Release engineering
- **Release alvo:** 1.0.1
- **Dependências:** Nenhuma

## Problema

O projeto declara `1.0.0` e uma API estável, mas ainda possui sinais
inconsistentes de projeto Alpha:

- `pyproject.toml` usa `Development Status :: 3 - Alpha`.
- `Python 3.10+` é requisito, porém 3.10 não aparece nos classifiers; 3.13
  aparece no metadata, mas não está na matriz do CI.
- O README referencia `LICENSE`, mas o arquivo não existe no repositório.
- README e release notes usam URLs de repositórios diferentes.
- A suíte emite o aviso de `pytest-asyncio` sobre o escopo padrão do event loop.

## Escopo

- Definir a matriz oficial de Python e alinhá-la entre `requires-python`,
  classifiers, CI e documentação.
- Substituir o classifier Alpha por `Production/Stable` se a promessa de
  `1.0.0` for mantida.
- Adicionar a licença MIT no caminho referenciado e verificar sua inclusão no
  pacote distribuído.
- Padronizar as URLs do projeto em README, metadata e release notes.
- Definir explicitamente o escopo do event loop assíncrono no `pyproject.toml`
  para eliminar o warning futuro do pytest-asyncio.
- Evitar divergência futura entre a versão publicada, `pyproject.toml` e
  `eizo.__version__`.

## Critérios de aceite

- [ ] O metadata descreve uma única política de suporte coerente com o CI.
- [ ] O pacote não se apresenta simultaneamente como Alpha e API estável.
- [ ] `LICENSE` existe, contém a licença MIT e é incluído no artefato
      distribuído.
- [ ] README, `pyproject.toml` e release notes apontam para o mesmo repositório.
- [ ] A suíte não emite o warning de escopo padrão do pytest-asyncio.
- [ ] A versão reportada por `python -m eizo --version` coincide com a versão
      do pacote construído.

## Verificação

```bash
python -m ruff check src/eizo/ tests/
python -m mypy src/eizo/
python -m pytest -q
python -m build
```

Inspecionar o wheel e o sdist gerados para confirmar a presença de README,
licença e metadata correto. Remover artefatos de build antes de concluir a
task, caso não sejam versionados.

## Não escopo

Reescrever o histórico Git ou criar retroativamente tags ausentes. Eventuais
diferenças históricas devem ser documentadas sem alterar commits antigos.
