# Eizō 1.0.0 — Release Notes

**Data**: 2026-08-10

## O que é

**Eizō (映像)** é uma CLI Python que parseia codebases com **Tree-sitter**,
constrói um **knowledge graph** de código em **SQLite**, e expõe consultas
via **CLI** e **servidor MCP** (Model Context Protocol) para agentes LLM.

A versão 1.0.0 marca a **estabilização da API pública**: a superfície
definida no Sprint 9 (contrato de compatibilidade + deprecation policy)
passa a ser prometida — nada quebra a partir daqui sem o ciclo de
deprecation de duas versões.

## Destaques

- **8 linguagens** com parsers Tree-sitter: Python, TypeScript/JavaScript,
  Go, Rust, Java, C#, PHP e Ruby
- **API pública estável** — `__all__` explícito, contrato documentado em
  `docs/api.md`, deprecation policy de 2 versões
- **16 comandos CLI** (Click + Rich): init, watch, diff (1 ou 2 refs),
  search, trace, why, impact, arch, dead, cycles, hotspots, metrics,
  export, architecture, mcp, status
- **Export em 6 formatos**: DOT, Mermaid, JSON, HTML 3D, **SVG** e **PNG**
  (SVG/PNG via graphviz)
- **Servidor MCP** com 8 ferramentas (SSE e stdio)
- **Indexação incremental** com detecção de arquivos criados, modificados
  e removidos; suporte a `.gitignore`/`.eizoignore`
- **CI multi-OS**: Ubuntu, macOS e Windows × Python 3.10/3.11/3.12
- Robustez: captura de chamadas dentro de macros Rust, fuzz tests
  determinísticos dos parsers, benchmark de indexação em escala

## Requisitos

- **Python 3.10+**
- **Graphviz (opcional)**: necessário apenas para `eizo export svg` e
  `eizo export png` — binário de sistema, não é dependência Python:
  - Debian/Ubuntu: `apt install graphviz`
  - macOS: `brew install graphviz`
  - Windows: `choco install graphviz` (ou instalador do site oficial)

## Instalação

```bash
git clone https://github.com/walternagai/eizo.git
cd eizo
make install
# ou: pip install -e ".[dev]"
```

No Windows, use `py -m pip install -e ".[dev]"` (o `make` não existe por
padrão).

## Breaking changes

**Nenhuma.** A API pública foi congelada no 0.3.0 (Sprint 9) e esta release
não remove nem renomeia símbolo público, comando ou opção. O único
comportamento novo é aditivo: `eizo export` aceita os formatos `svg` e
`png`.

## Changelog

Ver [CHANGELOG.md](../CHANGELOG.md) para o histórico completo.
