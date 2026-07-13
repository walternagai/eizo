"""CLI principal do Eizō — Codebase Knowledge Graph.

Comandos:
  eizo init     Indexa o repositório atual
  eizo search   Busca símbolos no grafo
  eizo trace    Traça call graph de um símbolo
  eizo impact   Analisa impacto de mudança
  eizo arch     Mostra visão arquitetural
  eizo mcp      Inicia servidor MCP
  eizo status   Estatísticas do grafo
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from eizo.graph.store import GraphStore
from eizo.indexer import index_repository
from eizo.queries.impact import analyze_impact
from eizo.queries.search import search_symbols
from eizo.queries.trace import trace_call_path

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="eizo")
def main() -> None:
    """映像 — Codebase Knowledge Graph CLI.

    Parseia codebases com Tree-sitter, constrói grafo de conhecimento
    em SQLite, e expõe queries via CLI e MCP.
    """


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--rebuild", is_flag=True, help="Reconstrói o grafo do zero")
def init(path: str, rebuild: bool) -> None:
    """Indexa um repositório no grafo de conhecimento."""
    repo_path = Path(path).resolve()
    store = GraphStore(repo_path)

    if rebuild:
        console.print("[yellow]Reconstruindo grafo do zero...[/yellow]")
        store.clear_all()

    index_repository(repo_path, store)


@main.command()
@click.argument("query")
@click.option("--kind", help="Filtrar por tipo (function, class, method, import)")
@click.option("--language", help="Filtrar por linguagem (python, typescript)")
@click.option("--limit", default=20, help="Limite de resultados")
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
def search(
    query: str,
    kind: str | None,
    language: str | None,
    limit: int,
    repo_path: str,
) -> None:
    """Busca símbolos no grafo de conhecimento."""
    store = GraphStore(Path(repo_path).resolve())
    results = search_symbols(store, query, kind=kind, language=language, limit=limit)

    if not results:
        console.print("[yellow]Nenhum resultado encontrado.[/yellow]")
        return

    table = Table(title=f"Resultados para '{query}'")
    table.add_column("Nome", style="cyan")
    table.add_column("Tipo", style="green")
    table.add_column("Linguagem", style="blue")
    table.add_column("Arquivo", style="white")
    table.add_column("Linha", style="dim")

    for node in results:
        table.add_row(
            node.name,
            node.kind,
            node.language,
            node.file_path,
            str(node.line_start or ""),
        )

    console.print(table)
    console.print(f"[dim]{len(results)} resultado(s)[/dim]")


@main.command()
@click.argument("symbol")
@click.option("--direction", type=click.Choice(["incoming", "outgoing", "both"]), default="both")
@click.option("--depth", default=3, help="Profundidade máxima")
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
def trace(symbol: str, direction: str, depth: int, repo_path: str) -> None:
    """Traça o call graph de um símbolo."""
    store = GraphStore(Path(repo_path).resolve())
    result = trace_call_path(store, symbol, direction=direction, max_depth=depth)

    if result["symbol"] is None:
        console.print(f"[red]Símbolo '{symbol}' não encontrado.[/red]")
        return

    sym = result["symbol"]
    loc = f"{sym.file_path}:{sym.line_start}"
    console.print(f"[bold]Call graph para:[/bold] [cyan]{sym.name}[/cyan] ({sym.kind}, {loc})")

    if result["callers"]:
        console.print("\n[bold]⬆ Quem chama:[/bold]")
        _print_call_tree(result["callers"], "callers")

    if result["callees"]:
        console.print("\n[bold]⬇ Quem é chamado:[/bold]")
        _print_call_tree(result["callees"], "callees")


def _print_call_tree(items: list[dict[str, Any]], key: str, indent: int = 0) -> None:
    """Imprime árvore de chamadas recursivamente."""
    prefix = "  " * indent
    for item in items:
        node = item["node"]
        console.print(f"{prefix}• [cyan]{node.name}[/cyan] ({node.kind}, {node.file_path}:{node.line_start})")
        if key in item:
            _print_call_tree(item[key], key, indent + 1)


@main.command()
@click.argument("symbol")
@click.option("--depth", default=3, help="Profundidade máxima")
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
def impact(symbol: str, depth: int, repo_path: str) -> None:
    """Analisa o impacto de mudança em um símbolo."""
    store = GraphStore(Path(repo_path).resolve())
    result = analyze_impact(store, symbol, max_depth=depth)

    if result["symbol"] is None:
        console.print(f"[red]Símbolo '{symbol}' não encontrado.[/red]")
        return

    sym = result["symbol"]
    loc = f"{sym.file_path}:{sym.line_start}"
    console.print(f"[bold]Análise de impacto para:[/bold] [cyan]{sym.name}[/cyan] ({sym.kind}, {loc})")

    if not result["impact_chain"]:
        console.print("[yellow]Nenhum dependente encontrado.[/yellow]")
        return

    tree = Tree(f"[bold]{sym.name}[/bold]")
    _build_impact_tree(tree, result["impact_chain"])
    console.print(tree)


def _build_impact_tree(tree: Tree, chain: list[dict[str, Any]]) -> None:
    """Constrói árvore de impacto recursivamente."""
    for item in chain:
        node = item["node"]
        relation = item.get("relation", "")
        label = f"[cyan]{node.name}[/cyan] ({node.kind}) — [dim]{relation}[/dim]"
        branch = tree.add(label)
        if "dependents" in item:
            _build_impact_tree(branch, item["dependents"])


@main.command()
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
def arch(repo_path: str) -> None:
    """Mostra visão arquitetural do repositório."""
    store = GraphStore(Path(repo_path).resolve())
    stats = store.get_stats()

    if stats.total_nodes == 0:
        console.print("[yellow]Grafo vazio. Execute 'eizo init' primeiro.[/yellow]")
        return

    console.print("[bold]Visão Arquitetural[/bold]\n")

    # Por linguagem
    table = Table(title="Linguagens")
    table.add_column("Linguagem", style="blue")
    table.add_column("Nós", style="cyan")
    table.add_column("Arquivos", style="white")
    for lang, count in stats.by_language.items():
        table.add_row(lang, str(count), str(stats.total_files))
    console.print(table)

    # Por tipo de nó
    table2 = Table(title="Símbolos por Tipo")
    table2.add_column("Tipo", style="green")
    table2.add_column("Quantidade", style="cyan")
    for kind, count in stats.by_kind.items():
        table2.add_row(kind, str(count))
    console.print(table2)

    # Por tipo de aresta
    table3 = Table(title="Relações por Tipo")
    table3.add_column("Relação", style="yellow")
    table3.add_column("Quantidade", style="cyan")
    for kind, count in stats.by_edge_kind.items():
        table3.add_row(kind, str(count))
    console.print(table3)

    console.print(f"\n[dim]Total: {stats.total_nodes} nós, {stats.total_edges} arestas, "
                  f"{stats.total_files} arquivos, {stats.db_size_bytes / 1024:.1f} KB[/dim]")


@main.command()
@click.option("--port", default=8765, help="Porta do servidor MCP")
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
def mcp(port: int, repo_path: str) -> None:
    """Inicia o servidor MCP para agentes LLM."""
    from eizo.mcp.server import serve_mcp

    store = GraphStore(Path(repo_path).resolve())
    serve_mcp(store, port)


@main.command()
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
def status(repo_path: str) -> None:
    """Mostra estatísticas do grafo de conhecimento."""
    store = GraphStore(Path(repo_path).resolve())
    stats = store.get_stats()

    if stats.total_nodes == 0:
        console.print("[yellow]Grafo vazio. Execute 'eizo init' primeiro.[/yellow]")
        return

    console.print("[bold]Status do Grafo[/bold]\n")

    table = Table(show_header=False)
    table.add_column("Métrica", style="blue")
    table.add_column("Valor", style="cyan")

    table.add_row("Nós", str(stats.total_nodes))
    table.add_row("Arestas", str(stats.total_edges))
    table.add_row("Arquivos", str(stats.total_files))
    table.add_row("Linguagens", ", ".join(stats.by_language.keys()))
    table.add_row("Tamanho do banco", f"{stats.db_size_bytes / 1024:.1f} KB")
    table.add_row("Caminho", str(store.db_path))

    console.print(table)
