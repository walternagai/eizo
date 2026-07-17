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
# Indexa o diretório atual (incremental — pula arquivos inalterados)
eizo init

# Indexa um diretório específico
eizo init /caminho/do/projeto

# Força reindexação de todos os arquivos
eizo init --force

# Reconstrói o grafo do zero (limpa DB + reindexa tudo)
eizo init --rebuild
```

A indexação é **incremental**: arquivos cujo conteúdo (hash SHA-256) não mudou
desde a última indexação são pulados automaticamente. Use `--force` ou `--rebuild`
para forçar reindexação completa.

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

### Detectar código morto

```bash
# Lista símbolos definidos sem nenhum caller/import
eizo dead

# Exclui entrypoints customizados
eizo dead --entrypoint my_handler --entrypoint my_cli
```

Símbolos como `main`, `run`, `serve`, `cli`, `app`, `create_app`, `setup`,
`teardown`, `handle` são considerados entrypoints por padrão e excluídos
da análise.

### Hotspots (símbolos críticos)

```bash
# Top 20 símbolos mais referenciados
eizo hotspots

# Top 50 com mínimo de 5 referências
eizo hotspots --limit 50 --min-refs 5
```

Símbolos com muitas referências são pontos críticos — mudanças neles têm
alto impacto na base de código.

### Exportar grafo

```bash
# Exporta para Graphviz DOT
eizo export dot -o graph.dot
dot -Tpng graph.dot -o graph.png  # renderiza com Graphviz

# Exporta para Mermaid (renderiza em GitHub, GitLab, Notion)
eizo export mermaid --kind class --edge-kind inherits

# Exporta para JSON
eizo export json --language python --limit 50 -o graph.json

# Diagrama de classes Mermaid
eizo export mermaid --diagram-type classDiagram
```

Filtros disponíveis: `--kind`, `--language`, `--limit`, `--edge-kind` (múltiplo).

### Visualizar em 3D

```bash
# Gera um HTML autocontido (offline, sem dependência de rede) com o grafo
# navegável em 3D: rotação/zoom, destaque de vizinhos ao passar o mouse,
# painel de detalhes ao clicar em um nó, e busca por nome
eizo export html -o graph.html

# abra graph.html no navegador

# Os mesmos filtros de --kind/--language/--limit/--edge-kind se aplicam,
# útil para focar em uma parte do grafo (ex: apenas hierarquia de classes)
eizo export html --kind class --edge-kind inherits -o classes.html
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
# Inicia servidor MCP com transporte SSE (HTTP) na porta 8765
eizo mcp

# Porta customizada
eizo mcp --port 9090

# Transporte stdio (padrão para agents locais como Claude Code)
eizo mcp --transport stdio

# Repositório específico
eizo mcp --path /caminho/do/projeto
```

O servidor expõe 7 ferramentas MCP:

| Tool | Descrição |
|------|-----------|
| `search_symbols` | Busca símbolos por nome |
| `get_symbol_context` | Contexto completo de um símbolo |
| `trace_call_path` | Call graph de/para um símbolo |
| `analyze_impact` | Cadeia de dependências |
| `get_architecture` | Visão arquitetural do repositório |
| `find_dead_code_symbols` | Detecta código morto |
| `get_hotspots` | Símbolos mais referenciados |

### Status

```bash
eizo status
```

## Comandos

| Comando | Descrição |
|---------|-----------|
| `eizo init [path]` | Indexa repositório no grafo (incremental) |
| `eizo search <query>` | Busca símbolos |
| `eizo trace <symbol>` | Call graph |
| `eizo impact <symbol>` | Análise de impacto |
| `eizo arch` | Visão arquitetural |
| `eizo dead` | Detecta código morto (sem callers) |
| `eizo hotspots` | Símbolos mais referenciados |
| `eizo export dot\|mermaid\|json` | Exporta grafo para visualização |
| `eizo mcp` | Servidor MCP |
| `eizo status` | Estatísticas do grafo |

### Opção global `--format json`

Todos os comandos de consulta suportam `--format json` para piping em scripts e agents:

```bash
eizo --format json search "UserModel" | jq '.[0].file_path'
eizo --format json dead | jq 'length'
eizo --format json hotspots --min-refs 3 | jq '.[] | .node.name'
```

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
