# TASK-004 — Expandir fuzzing para os oito parsers

- **Status:** Concluída
- **Prioridade:** P2
- **Tipo:** Robustez
- **Release alvo:** 1.1.0
- **Dependências:** TASK-002 recomendada

## Problema

O projeto suporta oito linguagens, mas `tests/test_parser_fuzz.py` cobre apenas
Python, TypeScript, Go, Rust e Java. C#, PHP e Ruby possuem testes funcionais,
porém não recebem a mesma proteção contra entradas malformadas, caracteres de
controle e entradas aleatórias.

## Escopo

- Incluir C#, PHP e Ruby no corpus fuzz determinístico existente.
- Manter seed fixa e o comportamento reprodutível da suíte.
- Adicionar alguns casos malformados específicos de cada gramática, sem exigir
  expansão indiscriminada do corpus.
- Garantir que o parser nunca levante exceção para os inputs aceitos pelo
  contrato atual do indexador.
- Registrar claramente no teste a cobertura das oito linguagens.

## Critérios de aceite

- [x] Os oito parsers aparecem no teste fuzz e executam no CI completo.
- [x] Inputs vazios, inválidos, com Unicode, caracteres de controle e casos
      específicos de cada linguagem não causam crash.
- [x] A seed continua reproduzindo exatamente os mesmos casos em cada execução.
- [x] O teste mantém as invariantes mínimas: listas de nós/arestas e nó de
      arquivo quando aplicável.
- [x] Nenhuma exceção é escondida com `xfail`, `skip` ou `except` no teste.
- [x] A cobertura global continua acima de 70% e o tempo do CI permanece
      aceitável.

## Verificação

```bash
python -m pytest tests/test_parser_fuzz.py tests/test_parser_*_extended.py -q
python -m ruff check src/eizo/ tests/
python -m pytest --cov=src/eizo --cov-fail-under=70 -q
```

## Não escopo

Corrigir limitações semânticas já documentadas, como resolução heurística de
imports, ou transformar os parsers em analisadores completos de tipos.
