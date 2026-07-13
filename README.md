# Eizō (映像) — Codebase Knowledge Graph CLI

映像 — "imagem/reflexão". Reflete a estrutura do código como um grafo de conhecimento.

## Visão Geral

**Eizō** é uma CLI Python que parseia codebases com **Tree-sitter**, constrói um **knowledge graph** de código em **SQLite**, e expõe consultas via **CLI** e **servidor MCP** (Model Context Protocol) para agentes LLM.

### Para que serve?

- **Desenvolvedores**: entenda a arquitetura de qualquer repositório sem ler arquivo por arquivo
- **Agentes LLM**: dê contexto estrutural para Claude Code, Cline, Roo Code, Continue e outros via MCP
- **Onboarding**: novos membros do time exploram o grafo em vez de grep cego
- **Análise de impacto**: antes de mudar um símbolo, veja toda a cadeia de dependências

## Stack

| Camada | Tecnologia |
|--------|-----------|
| CLI | Python 3.10+ / Click / Rich |
| Parsing | Tree-sitter (Python + TypeScript/JavaScript) |
| Grafo | SQLite (WAL mode, FTS5) |
| MCP | `mcp` Python SDK |
| Testes | pytest + pytest-cov |
| Lint | Ruff + mypy |

## Instalação

```bash
# Clone o repositório
git clone https://github.com/ninja-apps/eizo.git
cd eizo

# Instale com dependências de desenvolvimento
make install
# ou: pip install -e ".[dev]"
```

## Uso

### Indexar um repositório

```bash
# Indexa o diretório atual
eizo init

# Indexa um diretório específico
eizo init /caminho/do/projeto

# Reconstrói o grafo do zero
eizo init --rebuild
```

### Buscar símbolos

```bash
# Busca por nome
eizo search "get_user"

# Filtra por tipo e linguagem
eizo search "User" --kind class --language python

# Limita resultados
eizo search "helper" --limit 5
```

### Traçar call graph

```bash
# Quem chama e quem é chamado
eizo trace "processar_pagamento"

# Apenas quem chama
eizo trace "calcular_total" --direction incoming

# Apenas quem é chamado
eizo trace "main" --direction outgoing

# Profundidade maior
eizo trace "iniciar" --depth 5
```

### Analisar impacto

```bash
# Cadeia de dependências de um símbolo
eizo impact "DatabaseConnection"

# Profundidade maior
eizo impact "UserModel" --depth 5
```

### Visão arquitetural

```bash
eizo arch
```

Exemplo de saída:

```
Linguagens
┏━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━┓
┃ Linguagem  ┃  Nós ┃ Arquivos ┃
┡━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━┩
│ python     │  156 │       12 │
│ typescript │   89 │        8 │
└────────────┴──────┴──────────┘

Símbolos por Tipo
┏━━━━━━━━━━┳━━━━━━━━━━┓
┃ Tipo     ┃ Qtde     ┃
┡━━━━━━━━━━╇━━━━━━━━━━┩
│ function │      120 │
│ class    │       35 │
│ import   │       60 │
│ method   │       30 │
└──────────┴──────────┘
```

### Servidor MCP

```bash
# Inicia servidor MCP na porta 8765
eizo mcp

# Porta customizada
eizo mcp --port 9090

# Repositório específico
eizo mcp --path /caminho/do/projeto
```

O servidor expõe 5 ferramentas MCP:

| Tool | Descrição |
|------|-----------|
| `search_symbols` | Busca símbolos por nome |
| `get_symbol_context` | Contexto completo de um símbolo |
| `trace_call_path` | Call graph de/para um símbolo |
| `analyze_impact` | Cadeia de dependências |
| `get_architecture` | Visão arquitetural do repositório |

### Status

```bash
eizo status
```

## Comandos

| Comando | Descrição |
|---------|-----------|
| `eizo init [path]` | Indexa repositório no grafo |
| `eizo search <query>` | Busca símbolos |
| `eizo trace <symbol>` | Call graph |
| `eizo impact <symbol>` | Análise de impacto |
| `eizo arch` | Visão arquitetural |
| `eizo mcp` | Servidor MCP |
| `eizo status` | Estatísticas do grafo |

## Desenvolvimento

```bash
make install      # instala com dev deps
make test         # roda pytest
make lint         # ruff check
make typecheck    # mypy
make check        # lint + typecheck + test
make coverage     # pytest com cobertura
```

## Estrutura do Projeto

```
eizo/
├── src/eizo/
│   ├── cli.py               # Entry point Click
│   ├── indexer.py           # Orquestrador de indexação
│   ├── graph/
│   │   ├── models.py        # Dataclasses Node, Edge
│   │   ├── schema.py        # Schema SQLite
│   │   └── store.py         # GraphStore CRUD
│   ├── parser/
│   │   ├── base.py          # Parser base abstrato
│   │   ├── python.py        # Parser Python
│   │   └── typescript.py    # Parser TS/JS
│   ├── queries/
│   │   ├── search.py        # Busca textual
│   │   ├── trace.py         # Call graph
│   │   └── impact.py        # Análise de impacto
│   └── mcp/
│       └── server.py        # Servidor MCP
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_schema.py
│   ├── test_store.py
│   ├── test_parser_base.py
│   ├── test_parser_python.py
│   ├── test_parser_typescript.py
│   ├── test_indexer.py
│   ├── test_queries_search.py
│   ├── test_queries_trace.py
│   └── test_queries_impact.py
├── pyproject.toml
├── Makefile
├── AGENTS.md
└── README.md
```

## Licença

MIT
