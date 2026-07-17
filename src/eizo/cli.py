"""CLI principal do Eizō — Codebase Knowledge Graph.

Comandos:
  eizo init     Indexa o repositório atual
  eizo search   Busca símbolos no grafo
  eizo trace    Traça call graph de um símbolo
  eizo impact   Analisa impacto de mudança
  eizo arch     Mostra visão arquitetural
  eizo mcp      Inicia servidor MCP
  eizo status   Estatísticas do grafo
  eizo dead     Detecta código morto (sem callers)
  eizo hotspots Mostra símbolos mais referenciados
  eizo export   Exporta grafo em DOT/Mermaid/JSON
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from eizo.graph.store import GraphStore
from eizo.indexer import index_repository
from eizo.queries.analysis import find_dead_code, find_hotspots
from eizo.queries.export import export_dot, export_json, export_mermaid
from eizo.queries.impact import analyze_impact
from eizo.queries.search import search_symbols
from eizo.queries.trace import trace_call_path

console = Console()


def _emit_json(data: Any) -> None:
    """Emite data como JSON na stdout (para piping em scripts/agents)."""
    click.echo(json.dumps(data, indent=2, default=str))


def _node_to_dict(node: Any) -> dict[str, Any]:
    """Converte Node para dict serializável (para --format json)."""
    return {
        "id": node.id,
        "name": node.name,
        "kind": node.kind,
        "file_path": node.file_path,
        "language": node.language,
        "line_start": node.line_start,
        "line_end": node.line_end,
        "docstring": node.docstring,
        "code_snippet": node.code_snippet,
    }


@click.group()
@click.version_option(version="0.1.0", prog_name="eizo")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Formato de saída: 'table' (padrão, rich) ou 'json' (para piping)",
)
@click.pass_context
def main(ctx: click.Context, output_format: str) -> None:
    """映像 — Codebase Knowledge Graph CLI.

    Parseia codebases com Tree-sitter, constrói grafo de conhecimento
    em SQLite, e expõe queries via CLI e MCP.
    """
    ctx.ensure_object(dict)
    ctx.obj["format"] = output_format


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--rebuild", is_flag=True, help="Reconstrói o grafo do zero")
@click.option("--force", is_flag=True, help="Força reindexação de todos os arquivos")
@click.pass_context
def init(ctx: click.Context, path: str, rebuild: bool, force: bool) -> None:
    """Indexa um repositório no grafo de conhecimento."""
    repo_path = Path(path).resolve()
    store = GraphStore(repo_path)

    if rebuild:
        console.print("[yellow]Reconstruindo grafo do zero...[/yellow]")
        store.clear_all()
        force = True

    index_repository(repo_path, store, force=force)

    if ctx.obj.get("format") == "json":
        stats = store.get_stats()
        _emit_json({
            "status": "ok",
            "repository": str(repo_path),
            "stats": {
                "total_nodes": stats.total_nodes,
                "total_edges": stats.total_edges,
                "total_files": stats.total_files,
                "by_language": stats.by_language,
            },
        })


@main.command()
@click.argument("query")
@click.option("--kind", help="Filtrar por tipo (function, class, method, import)")
@click.option("--language", help="Filtrar por linguagem (python, typescript)")
@click.option("--limit", default=20, help="Limite de resultados")
@click.option(
    "--full-text", "full_text", is_flag=True,
    help="Busca full-text (FTS5) sobre nome + docstring + code_snippet, ranqueada por relevância",
)
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    kind: str | None,
    language: str | None,
    limit: int,
    full_text: bool,
    repo_path: str,
) -> None:
    """Busca símbolos no grafo de conhecimento."""
    store = GraphStore(Path(repo_path).resolve())
    results = search_symbols(store, query, kind=kind, language=language, limit=limit, full_text=full_text)

    if ctx.obj.get("format") == "json":
        _emit_json([_node_to_dict(n) for n in results])
        return

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
@click.pass_context
def trace(ctx: click.Context, symbol: str, direction: str, depth: int, repo_path: str) -> None:
    """Traça o call graph de um símbolo."""
    repo = Path(repo_path).resolve()
    store = GraphStore(repo)
    result = trace_call_path(store, symbol, direction=direction, max_depth=depth)

    if ctx.obj.get("format") == "json":
        _emit_json({
            "symbol": _node_to_dict(result["symbol"]) if result["symbol"] else None,
            "callers": result["callers"],
            "callees": result["callees"],
        })
        return

    if result["symbol"] is None:
        console.print(f"[red]Símbolo '{symbol}' não encontrado.[/red]")
        return

    sym = result["symbol"]
    rel_path = _relative_path(sym.file_path, repo)
    loc = f"{rel_path}:{sym.line_start}"
    console.print(
        f"[bold]Call graph para:[/bold] [cyan]{sym.name}[/cyan] "
        f"({sym.kind}, {loc})"
    )
    if sym.docstring:
        first_line = sym.docstring.strip().splitlines()[0]
        if first_line:
            console.print(f"[dim]  {first_line}[/dim]")

    callers: list[dict[str, Any]] = result["callers"]
    callees: list[dict[str, Any]] = result["callees"]

    if direction in ("incoming", "both"):
        if callers:
            console.print("\n[bold]⬆ Quem chama:[/bold]")
            tree = Tree("")
            _build_call_tree(tree, callers, "callers", repo)
            console.print(tree)
        else:
            console.print("\n[bold]⬆ Quem chama:[/bold] [dim]Nenhum caller encontrado.[/dim]")

    if direction in ("outgoing", "both"):
        if callees:
            console.print("\n[bold]⬇ Quem é chamado:[/bold]")
            tree = Tree("")
            _build_call_tree(tree, callees, "callees", repo)
            console.print(tree)
        else:
            console.print("\n[bold]⬇ Quem é chamado:[/bold] [dim]Nenhuma callee encontrada.[/dim]")

    # Sumário
    n_callers = _count_nodes(callers)
    n_callees = _count_nodes(callees)
    depth_candidates = [_max_depth(callers, "callers"), _max_depth(callees, "callees")]
    max_depth_seen = max(depth_candidates) if depth_candidates else 0
    console.print(
        f"\n[dim]{n_callers} caller(s), {n_callees} callee(s), "
        f"profundidade máx: {max_depth_seen}[/dim]"
    )


def _relative_path(file_path: str, repo_root: Path) -> str:
    """Retorna path relativo a repo_root quando possível; absoluto caso contrário."""
    try:
        return str(Path(file_path).resolve().relative_to(repo_root))
    except (ValueError, OSError):
        return file_path


def _build_call_tree(tree: Tree, items: list[dict[str, Any]], key: str, repo_root: Path) -> None:
    """Constrói árvore de chamadas recursivamente com rich.tree.Tree."""
    for item in items:
        node = item["node"]
        rel = _relative_path(node.file_path, repo_root)
        if item.get("cycle"):
            label = f"[cyan]{node.name}[/cyan] [yellow](cycle)[/yellow]"
        else:
            label = (
                f"[cyan]{node.name}[/cyan] [dim]({node.kind}, {rel}:{node.line_start})[/dim]"
            )
        branch = tree.add(label)
        if key in item:
            _build_call_tree(branch, item[key], key, repo_root)


def _count_nodes(items: list[dict[str, Any]]) -> int:
    """Conta o número total de nós em uma árvore de chamadas (inclusive ciclos)."""
    count = 0
    for item in items:
        count += 1
        if "callers" in item:
            count += _count_nodes(item["callers"])
        elif "callees" in item:
            count += _count_nodes(item["callees"])
    return count


def _max_depth(items: list[dict[str, Any]], key: str) -> int:
    """Retorna a profundidade máxima alcançada em uma árvore de chamadas."""
    best = 0
    for item in items:
        best = max(best, item.get("depth", 0))
        if key in item:
            best = max(best, _max_depth(item[key], key))
    return best


@main.command()
@click.argument("symbol")
@click.option("--depth", default=3, help="Profundidade máxima")
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
@click.pass_context
def impact(ctx: click.Context, symbol: str, depth: int, repo_path: str) -> None:
    """Analisa o impacto de mudança em um símbolo."""
    store = GraphStore(Path(repo_path).resolve())
    result = analyze_impact(store, symbol, max_depth=depth)

    if ctx.obj.get("format") == "json":
        _emit_json({
            "symbol": _node_to_dict(result["symbol"]) if result["symbol"] else None,
            "impact_chain": result["impact_chain"],
        })
        return

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
@click.pass_context
def arch(ctx: click.Context, repo_path: str) -> None:
    """Mostra visão arquitetural do repositório."""
    store = GraphStore(Path(repo_path).resolve())
    stats = store.get_stats()

    if ctx.obj.get("format") == "json":
        _emit_json({
            "total_nodes": stats.total_nodes,
            "total_edges": stats.total_edges,
            "total_files": stats.total_files,
            "by_language": stats.by_language,
            "by_kind": stats.by_kind,
            "by_edge_kind": stats.by_edge_kind,
            "db_size_bytes": stats.db_size_bytes,
        })
        return

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
@click.option("--port", default=8765, help="Porta do servidor MCP (transporte SSE)")
@click.option(
    "--transport",
    type=click.Choice(["sse", "stdio"]),
    default="sse",
    help="Transporte: 'sse' (HTTP) ou 'stdio' (local, padrão para agents)",
)
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
def mcp(port: int, transport: str, repo_path: str) -> None:
    """Inicia o servidor MCP para agentes LLM."""
    from eizo.mcp.server import serve_mcp

    store = GraphStore(Path(repo_path).resolve())
    # transport é validado por click.Choice(["sse", "stdio"]) — cast seguro
    serve_mcp(store, port, transport=transport)  # type: ignore[arg-type]


@main.command()
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
@click.pass_context
def status(ctx: click.Context, repo_path: str) -> None:
    """Mostra estatísticas do grafo de conhecimento."""
    store = GraphStore(Path(repo_path).resolve())
    stats = store.get_stats()

    if ctx.obj.get("format") == "json":
        _emit_json({
            "total_nodes": stats.total_nodes,
            "total_edges": stats.total_edges,
            "total_files": stats.total_files,
            "by_language": stats.by_language,
            "db_size_bytes": stats.db_size_bytes,
            "db_path": str(store.db_path),
        })
        return

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


@main.command()
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
@click.option(
    "--entrypoint",
    "entrypoints",
    multiple=True,
    help="Nomes de entrypoints a excluir (pode repetir). Padrão: main, run, serve, etc.",
)
@click.option("--limit", default=100, help="Máximo de resultados")
@click.pass_context
def dead(ctx: click.Context, repo_path: str, entrypoints: tuple[str, ...], limit: int) -> None:
    """Detecta código morto — símbolos definidos sem nenhum caller/import."""
    store = GraphStore(Path(repo_path).resolve())
    eps = frozenset(entrypoints) if entrypoints else None
    results = find_dead_code(store, entrypoints=eps, limit=limit)

    if ctx.obj.get("format") == "json":
        _emit_json([_node_to_dict(n) for n in results])
        return

    if not results:
        console.print("[green]✓ Nenhum código morto encontrado![/green]")
        return

    console.print(f"[bold]Código morto detectado[/bold] ({len(results)} símbolo(s))\n")

    table = Table(title="Símbolos sem referências")
    table.add_column("Nome", style="cyan")
    table.add_column("Tipo", style="green")
    table.add_column("Arquivo", style="white")
    table.add_column("Linha", style="dim")

    for node in results:
        table.add_row(
            node.name,
            node.kind,
            node.file_path,
            str(node.line_start or ""),
        )

    console.print(table)
    console.print(
        "\n[dim]Dica: símbolos como 'main', 'serve', 'cli' são considerados "
        "entrypoints e excluídos por padrão. Use --entrypoint para adicionar outros.[/dim]"
    )


@main.command()
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
@click.option("--limit", default=20, help="Máximo de resultados")
@click.option("--min-refs", default=2, help="Mínimo de referências para aparecer")
@click.pass_context
def hotspots(
    ctx: click.Context,
    repo_path: str,
    limit: int,
    min_refs: int,
) -> None:
    """Mostra símbolos mais referenciados (pontos críticos de acoplamento)."""
    store = GraphStore(Path(repo_path).resolve())
    results = find_hotspots(store, limit=limit, min_references=min_refs)

    if ctx.obj.get("format") == "json":
        _emit_json([
            {"node": _node_to_dict(r["node"]), "reference_count": r["reference_count"]}
            for r in results
        ])
        return

    if not results:
        console.print("[yellow]Nenhum hotspot encontrado (baixe --min-refs se necessário).[/yellow]")
        return

    console.print("[bold]Hotspots[/bold] — símbolos mais referenciados\n")

    table = Table(title=f"Top {len(results)} símbolos por referências")
    table.add_column("#", style="dim")
    table.add_column("Nome", style="cyan")
    table.add_column("Tipo", style="green")
    table.add_column("Refs", style="yellow", justify="right")
    table.add_column("Arquivo", style="white")
    table.add_column("Linha", style="dim")

    for i, item in enumerate(results, 1):
        node = item["node"]
        table.add_row(
            str(i),
            node.name,
            node.kind,
            str(item["reference_count"]),
            node.file_path,
            str(node.line_start or ""),
        )

    console.print(table)
    console.print(
        "\n[dim]Símbolos com muitas referências são pontos críticos — "
        "mudanças neles têm alto impacto.[/dim]"
    )


@main.command()
@click.argument("format", type=click.Choice(["dot", "mermaid", "json"]))
@click.option("--kind", help="Filtrar nós por tipo (function, class, method)")
@click.option("--language", help="Filtrar nós por linguagem (python, typescript)")
@click.option("--limit", default=None, type=int, help="Máximo de nós")
@click.option(
    "--edge-kind",
    "edge_kinds",
    multiple=True,
    help="Filtrar arestas por tipo (calls, imports, inherits, contains). Pode repetir.",
)
@click.option(
    "--diagram-type",
    type=click.Choice(["flowchart", "classDiagram"]),
    default="flowchart",
    help="Tipo de diagrama Mermaid (apenas para format=mermaid)",
)
@click.option("--output", "-o", type=click.Path(), help="Arquivo de saída (padrão: stdout)")
@click.option("--path", "repo_path", default=".", help="Caminho do repositório")
def export(
    format: str,
    kind: str | None,
    language: str | None,
    limit: int | None,
    edge_kinds: tuple[str, ...],
    diagram_type: str,
    output: str | None,
    repo_path: str,
) -> None:
    """Exporta o grafo em formato DOT, Mermaid ou JSON.

    \b
    Exemplos:
      eizo export dot -o graph.dot
      eizo export mermaid --kind class --edge-kind inherits
      eizo export json --language python --limit 50
    """
    store = GraphStore(Path(repo_path).resolve())
    eps = frozenset(edge_kinds) if edge_kinds else None

    if format == "dot":
        result = export_dot(store, kind=kind, language=language, limit=limit, edge_kinds=eps)
    elif format == "mermaid":
        result = export_mermaid(
            store, kind=kind, language=language, limit=limit,
            edge_kinds=eps, diagram_type=diagram_type,
        )
    else:  # json
        result = export_json(store, kind=kind, language=language, limit=limit, edge_kinds=eps)

    if output:
        Path(output).write_text(result, encoding="utf-8")
        console.print(f"[green]✓ Grafo exportado para {output}[/green]")
    else:
        # Saída direta na stdout (sem rich formatting)
        click.echo(result)
