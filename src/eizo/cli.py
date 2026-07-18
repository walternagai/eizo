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
  eizo export   Exporta grafo em DOT/Mermaid/JSON/HTML (3D)
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import click
from click.shell_completion import get_completion_class
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from eizo.graph.store import GraphStore
from eizo.indexer import index_repository
from eizo.queries.analysis import find_dead_code, find_hotspots
from eizo.queries.export import (
    export_architecture_mermaid,
    export_dot,
    export_html,
    export_json,
    export_mermaid,
)
from eizo.queries.impact import analyze_impact
from eizo.queries.search import search_symbols
from eizo.queries.trace import trace_call_path

console = Console()
_force_color: bool | None = None
logger = logging.getLogger("eizo")


def _setup_logging(verbosity: int, quiet: bool) -> None:
    """Configura nível do logger eizo a partir de -v/-vv/--quiet."""
    if quiet:
        level = logging.ERROR
    elif verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)


def _emit_json(data: Any) -> None:
    """Emite data como JSON na stdout (para piping em scripts/agents)."""
    click.echo(json.dumps(data, indent=2, default=str))


def _repo_option() -> Callable[..., Any]:
    """Retorna decorator Click para a opção --repo (alias -C)."""
    return click.option(
        "--repo",
        "-C",
        "repo_path",
        default=".",
        help="Caminho do repositório",
    )


def _depth_option(default: int = 3) -> Callable[..., Any]:
    """Retorna decorator Click para --depth com validação 1..10."""
    return click.option(
        "--depth",
        default=default,
        type=click.IntRange(min=1, max=10),
        help="Profundidade máxima",
    )


def _limit_option(
    default: int = 20,
    help_text: str = "Limite de resultados",
) -> Callable[..., Any]:
    """Retorna decorator Click para --limit com validação >=1."""
    return click.option(
        "--limit",
        default=default,
        type=click.IntRange(min=1),
        help=help_text,
    )


def _node_to_dict(node: Any) -> dict[str, Any]:
    """Converte Node para dict serializável (para --output-format json)."""
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


def _env_value(key: str) -> str | None:
    """Retorna valor de variável de ambiente EIZO_<KEY> se definida."""
    return os.environ.get(f"EIZO_{key.upper()}")


def _env_bool(key: str) -> bool | None:
    """Interpreta variável de ambiente como booleano.

    Valores considerados True: 1, true, yes, on (case-insensitive).
    Qualquer outro valor não-vazio é False.
    """
    value = _env_value(key)
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "on"}


def _load_config(repo_path: Path, config_path: Path | None) -> dict[str, Any]:
    """Carrega configuração JSON de --config, EIZO_CONFIG ou .eizo/config.json.

    Prioridade de busca:
      --config > EIZO_CONFIG > .eizo/config.json
    Valores inválidos geram aviso e retornam dict vazio.
    """
    candidates: list[Path] = []
    if config_path:
        candidates.append(config_path)
    else:
        env_config = _env_value("config")
        if env_config:
            candidates.append(Path(env_config))
        candidates.append(repo_path / ".eizo" / "config.json")

    for candidate in candidates:
        if candidate.exists():
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return raw
            except json.JSONDecodeError:
                console.print(
                    f"[yellow]Aviso: config inválido em {candidate} — ignorado.[/yellow]"
                )
    return {}


def _merge_config(
    ctx: click.Context,
    command_defaults: dict[str, dict[str, Any]] | None = None,
    command_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Carrega config e retorna valores finais (CLI > env > config > defaults).

    Para cada chave, se o valor passado pelo CLI for igual ao default do
    Click e o config.json tiver outro valor, usa o do config. Campos
    explicitamente passados como flags globais (--output-format, --no-color)
    são respeitados e nunca sobrescritos pelo config/env.
    """
    repo_path: str | None = command_values.get("repo_path") if command_values else None
    if repo_path is None:
        repo_path = "."

    # EIZO_REPO só é aplicado se --repo não foi explicitado (valor igual ao default)
    env_repo = _env_value("repo")
    if env_repo and repo_path == ".":
        repo_path = env_repo

    config_path: Path | None = ctx.obj.get("config_path")
    cfg = _load_config(Path(repo_path).resolve(), config_path)

    # Campos globais (CLI > env > config)
    if not ctx.obj.get("format_explicit"):
        if "output_format" in cfg:
            ctx.obj["format"] = cfg["output_format"]
        env_format = _env_value("output_format")
        if env_format:
            ctx.obj["format"] = env_format

    if not ctx.obj.get("no_color_explicit"):
        if "no_color" in cfg and cfg["no_color"]:
            console._color_system = None
        env_no_color = _env_bool("no_color")
        if env_no_color is True or os.environ.get("NO_COLOR"):
            console._color_system = None

    merged: dict[str, Any] = {}
    if command_values and command_defaults:
        for key, value in command_values.items():
            defaults = command_defaults.get(key)
            env_val: Any = None
            if key == "repo_path" and repo_path != ".":
                env_val = repo_path
            elif key in {"limit", "depth", "min_refs", "full_text"}:
                env_val = _env_value(key)
                if env_val is not None and key in {"limit", "depth", "min_refs"}:
                    try:
                        env_val = int(env_val)
                    except ValueError:
                        env_val = None
                if env_val is not None and key == "full_text":
                    env_val = env_val.lower() in {"1", "true", "yes", "on"}

            default_value = defaults["default"] if defaults else None
            if env_val is not None and value == default_value:
                merged[key] = env_val
            elif defaults is None or value != default_value:
                merged[key] = value
            elif key in cfg:
                merged[key] = cfg[key]
            else:
                merged[key] = value
    elif command_values:
        merged = command_values.copy()
        if "repo_path" in merged and repo_path != "." and merged["repo_path"] == ".":
            merged["repo_path"] = repo_path

    return merged


def _install_completion(shell: str) -> str:
    """Gera ou instala script de shell completion para eizo.

    Retorna o script como string para ser exibido ou redirecionado.
    """
    cls = get_completion_class(shell)
    if cls is None:
        return f"Shell '{shell}' não suportado. Use bash, zsh ou fish."
    complete = cls(
        cli=main,
        ctx_args={},
        prog_name="eizo",
        complete_var="_EIZO_COMPLETE",
    )
    return complete.source()


SUPPORTED_SHELLS = ("bash", "zsh", "fish")


def _is_explicit(ctx: click.Context, param_name: str) -> bool:
    """Retorna True se o parâmetro foi passado explicitamente via CLI."""
    source = ctx.get_parameter_source(param_name)
    return source == click.core.ParameterSource.COMMANDLINE


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="eizo")
@click.option(
    "--output-format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Formato de saída: 'table' (padrão, rich) ou 'json' (para piping)",
)
@click.option(
    "--no-color",
    "no_color",
    is_flag=True,
    default=False,
    help="Desativa cores na saída (útil para CI ou piping)",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Caminho alternativo para arquivo de configuração JSON",
)
@click.option(
    "--install-completion",
    "install_completion",
    type=click.Choice(SUPPORTED_SHELLS),
    default=None,
    help="Instala shell completion e sai (bash/zsh/fish)",
)
@click.option(
    "--show-completion",
    "show_completion",
    type=click.Choice(SUPPORTED_SHELLS),
    default=None,
    help="Mostra script de shell completion e sai (bash/zsh/fish)",
)
@click.option(
    "-v",
    "--verbose",
    "verbosity",
    count=True,
    help="Aumenta verbosidade (-v=INFO, -vv=DEBUG)",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Silencia mensagens de log (apenas erros)",
)
@click.pass_context
def main(
    ctx: click.Context,
    output_format: str,
    no_color: bool,
    config_path: str | None,
    install_completion: str | None,
    show_completion: str | None,
    verbosity: int,
    quiet: bool,
) -> None:
    """映像 — Codebase Knowledge Graph CLI.

    Parseia codebases com Tree-sitter, constrói grafo de conhecimento
    em SQLite, e expõe queries via CLI e MCP.
    """
    if install_completion:
        script = _install_completion(install_completion)
        click.echo(script)
        ctx.exit()

    if show_completion:
        script = _install_completion(show_completion)
        click.echo(script)
        ctx.exit()

    ctx.ensure_object(dict)
    _setup_logging(verbosity, quiet)
    ctx.obj["format"] = output_format
    ctx.obj["format_explicit"] = _is_explicit(ctx, "output_format")
    ctx.obj["no_color_explicit"] = _is_explicit(ctx, "no_color") or no_color
    ctx.obj["config_path_explicit"] = _is_explicit(ctx, "config_path")
    ctx.obj["config_path"] = Path(config_path) if config_path else None
    ctx.obj["config"] = {}
    ctx.obj["verbosity"] = verbosity
    ctx.obj["quiet"] = quiet
    global _force_color
    _force_color = not no_color
    if no_color:
        console._color_system = None


@main.command(
    short_help="Indexa um repositório",
    epilog="Exemplos:\n  eizo init\n  eizo init /caminho/do/repo --rebuild\n  eizo init --dry-run",
)
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--rebuild", is_flag=True, help="Reconstrói o grafo do zero")
@click.option("--force", is_flag=True, help="Força reindexação de todos os arquivos")
@click.option("--dry-run", is_flag=True, help="Lista arquivos que seriam indexados sem persistir")
@click.pass_context
def init(ctx: click.Context, path: str, rebuild: bool, force: bool, dry_run: bool) -> None:
    """Indexa um repositório no grafo de conhecimento."""
    repo_path = Path(path).resolve()
    store = GraphStore(repo_path)

    if dry_run:
        logger.info("Dry-run: descobrindo arquivos em %s", repo_path)
        files = cast(list[Path], index_repository(repo_path, store=None, dry_run=True))
        if ctx.obj.get("format") == "json":
            _emit_json({
                "dry_run": True,
                "repository": str(repo_path),
                "files": [str(f) for f in files],
                "count": len(files),
            })
            return
        console.print(f"[bold]Dry-run:[/bold] {len(files)} arquivo(s) seriam indexados em {repo_path}")
        for f in files:
            console.print(f"  {f}")
        return

    if rebuild:
        console.print("[yellow]Reconstruindo grafo do zero...[/yellow]")
        logger.info("Limpando grafo existente em %s", store.db_path)
        store.clear_all()
        force = True

    logger.info("Iniciando indexação de %s", repo_path)
    index_repository(repo_path, store, force=force)
    logger.info("Indexação concluída")

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


@main.command(
    short_help="Busca símbolos no grafo",
    epilog=(
        "Exemplos:\n"
        "  eizo search helper\n"
        "  eizo search pagamento --full-text\n"
        "  eizo search foo --kind function --lang python"
    ),
)
@click.argument("query")
@click.option("--kind", help="Filtrar por tipo (function, class, method, import)")
@click.option("--language", help="Filtrar por linguagem (python, typescript)")
@_limit_option(default=20, help_text="Limite de resultados")
@click.option(
    "--full-text", "full_text", is_flag=True,
    help="Busca full-text (FTS5) sobre nome + docstring + code_snippet, ranqueada por relevância",
)
@_repo_option()
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
    """Busca símbolos no grafo de conhecimento.

    Por padrão, procura no nome dos símbolos. Use --full-text para buscar
    também em docstrings e trechos de código (FTS5).
    """
    cfg = _merge_config(
        ctx,
        command_defaults={
            "limit": {"default": 20},
            "full_text": {"default": False},
        },
        command_values={"limit": limit, "full_text": full_text, "repo_path": repo_path},
    )
    repo_path = cfg.get("repo_path", repo_path)
    store = GraphStore(Path(repo_path).resolve())
    results = search_symbols(
        store, query,
        kind=kind, language=language,
        limit=int(cfg["limit"]), full_text=bool(cfg["full_text"]),
    )

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


@main.command(
    short_help="Traça call graph de um símbolo",
    epilog="Exemplos:\n  eizo trace main\n  eizo trace helper --direction incoming\n  eizo trace core --depth 5",
)
@click.argument("symbol")
@click.option("--direction", type=click.Choice(["incoming", "outgoing", "both"]), default="both")
@_depth_option(default=3)
@_repo_option()
@click.pass_context
def trace(ctx: click.Context, symbol: str, direction: str, depth: int, repo_path: str) -> None:
    """Traça o call graph de um símbolo.

    Mostra quem chama e quem é chamado a partir do símbolo informado.
    Use --direction incoming, outgoing ou both (padrão).
    """
    cfg = _merge_config(
        ctx,
        command_defaults={"depth": {"default": 3}},
        command_values={"depth": depth, "repo_path": repo_path},
    )
    repo_path = cfg.get("repo_path", repo_path)
    repo = Path(repo_path).resolve()
    store = GraphStore(repo)
    result = trace_call_path(store, symbol, direction=direction, max_depth=cfg["depth"])

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


@main.command(
    short_help="Analisa impacto de mudança em um símbolo",
    epilog="Exemplos:\n  eizo impact core\n  eizo impact Base --depth 5",
)
@click.argument("symbol")
@_depth_option(default=3)
@_repo_option()
@click.pass_context
def impact(ctx: click.Context, symbol: str, depth: int, repo_path: str) -> None:
    """Analisa o impacto de mudança em um símbolo.

    Lista os símbolos que dependem do símbolo informado (imports, chamadas,
    herança) até a profundidade especificada.
    """
    cfg = _merge_config(
        ctx,
        command_defaults={"depth": {"default": 3}},
        command_values={"depth": depth, "repo_path": repo_path},
    )
    repo_path = cfg.get("repo_path", repo_path)
    store = GraphStore(Path(repo_path).resolve())
    result = analyze_impact(store, symbol, max_depth=cfg["depth"])

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


@main.command(
    short_help="Mostra visão arquitetural",
    epilog="Exemplos:\n  eizo arch\n  eizo arch --repo /caminho/do/projeto",
)
@_repo_option()
@click.pass_context
def arch(ctx: click.Context, repo_path: str) -> None:
    """Mostra visão arquitetural do repositório."""
    cfg = _merge_config(ctx, command_values={"repo_path": repo_path})
    _render_arch(ctx, cfg.get("repo_path", repo_path))


def _render_arch(ctx: click.Context, repo_path: str, output: str | None = None) -> None:
    """Renderiza visão arquitetural (usada por `arch` e `architecture`)."""
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

    if output:
        result = export_architecture_mermaid(store)
        Path(output).write_text(result, encoding="utf-8")
        console.print(f"[green]✓ Diagrama de arquitetura exportado para {output}[/green]")


@main.command(
    short_help="Inicia servidor MCP para agentes LLM",
    epilog="Exemplos:\n  eizo mcp\n  eizo mcp --port 8765 --transport sse",
)
@click.option("--port", default=8765, type=click.IntRange(min=1, max=65535), help="Porta do servidor MCP")
@click.option(
    "--transport",
    type=click.Choice(["sse", "stdio"]),
    default="sse",
    help="Transporte: 'sse' (HTTP) ou 'stdio' (local, padrão para agents)",
)
@_repo_option()
def mcp(port: int, transport: str, repo_path: str) -> None:
    """Inicia o servidor MCP para agentes LLM."""
    from eizo.mcp.server import serve_mcp

    store = GraphStore(Path(repo_path).resolve())
    # transport é validado por click.Choice(["sse", "stdio"]) — cast seguro
    serve_mcp(store, port, transport=transport)  # type: ignore[arg-type]


@main.command(
    short_help="Mostra estatísticas do grafo",
    epilog="Exemplos:\n  eizo status\n  eizo status --repo /caminho/do/projeto",
)
@_repo_option()
@click.pass_context
def status(ctx: click.Context, repo_path: str) -> None:
    """Mostra estatísticas do grafo de conhecimento."""
    cfg = _merge_config(ctx, command_values={"repo_path": repo_path})
    repo_path = cfg.get("repo_path", repo_path)
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


@main.command(
    short_help="Detecta código morto",
    epilog="Exemplos:\n  eizo dead\n  eizo dead --entrypoint my_entry --limit 50",
)
@_repo_option()
@click.option(
    "--entrypoint",
    "entrypoints",
    multiple=True,
    help="Nomes de entrypoints a excluir (pode repetir). Padrão: main, run, serve, etc.",
)
@_limit_option(default=100, help_text="Máximo de resultados")
@click.pass_context
def dead(ctx: click.Context, repo_path: str, entrypoints: tuple[str, ...], limit: int) -> None:
    """Detecta código morto — símbolos definidos sem nenhum caller/import.
    """
    cfg = _merge_config(
        ctx,
        command_defaults={"limit": {"default": 100}},
        command_values={"limit": limit, "repo_path": repo_path},
    )
    repo_path = cfg.get("repo_path", repo_path)
    store = GraphStore(Path(repo_path).resolve())
    eps = frozenset(entrypoints) if entrypoints else None
    results = find_dead_code(store, entrypoints=eps, limit=cfg["limit"])

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


@main.command(
    short_help="Mostra símbolos mais referenciados",
    epilog="Exemplos:\n  eizo hotspots\n  eizo hotspots --min-refs 1 --limit 10",
)
@_repo_option()
@_limit_option(default=20, help_text="Máximo de resultados")
@click.option("--min-refs", default=2, type=click.IntRange(min=1), help="Mínimo de referências para aparecer")
@click.pass_context
def hotspots(
    ctx: click.Context,
    repo_path: str,
    limit: int,
    min_refs: int,
) -> None:
    """Mostra símbolos mais referenciados."""
    cfg = _merge_config(
        ctx,
        command_defaults={
            "limit": {"default": 20},
            "min_refs": {"default": 2},
        },
        command_values={"limit": limit, "min_refs": min_refs, "repo_path": repo_path},
    )
    repo_path = cfg.get("repo_path", repo_path)
    store = GraphStore(Path(repo_path).resolve())
    results = find_hotspots(store, limit=cfg["limit"], min_references=cfg["min_refs"])

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


@main.command(
    short_help="Exporta o grafo",
    epilog=(
        "Exemplos:\n"
        "  eizo export dot -o graph.dot\n"
        "  eizo export mermaid --kind class --edge-kind inherits\n"
        "  eizo export json --language python --limit 50"
    ),
)
@click.argument("format", type=click.Choice(["dot", "mermaid", "json", "html"]))
@click.option("--kind", help="Filtrar nós por tipo (function, class, method)")
@click.option("--language", help="Filtrar nós por linguagem (python, typescript)")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Máximo de nós")
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
@_repo_option()
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
    """Exporta o grafo em formato DOT, Mermaid, JSON ou HTML (tridimensional)."""
    store = GraphStore(Path(repo_path).resolve())
    eps = frozenset(edge_kinds) if edge_kinds else None

    if format == "dot":
        result = export_dot(store, kind=kind, language=language, limit=limit, edge_kinds=eps)
    elif format == "mermaid":
        result = export_mermaid(
            store, kind=kind, language=language, limit=limit,
            edge_kinds=eps, diagram_type=diagram_type,
        )
    elif format == "html":
        result = export_html(store, kind=kind, language=language, limit=limit, edge_kinds=eps)
    else:  # json
        result = export_json(store, kind=kind, language=language, limit=limit, edge_kinds=eps)

    if output:
        Path(output).write_text(result, encoding="utf-8")
        console.print(f"[green]✓ Grafo exportado para {output}[/green]")
    else:
        # Saída direta na stdout (sem rich formatting)
        click.echo(result)



@main.command(
    short_help="Gera diagrama de arquitetura (alias de arch)", name="architecture"
)
@click.option("--output", "-o", type=click.Path(), help="Arquivo de saída (padrão: stdout)")
@_repo_option()
@click.pass_context
def architecture(
    ctx: click.Context,
    repo_path: str,
    output: str | None,
) -> None:
    """Gera diagrama de arquitetura em Mermaid do repositório indexado.

    Alias do comando arch. Mantido para compatibilidade.

    Quando usado sem -o, mostra a mesma visão arquitetural de arch.
    Com -o, exporta o diagrama Mermaid de arquitetura para o arquivo.
    """
    cfg = _merge_config(ctx, command_values={"repo_path": repo_path})
    _render_arch(ctx, cfg.get("repo_path", repo_path), output=output)
