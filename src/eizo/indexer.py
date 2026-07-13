"""Indexer — orquestrador que percorre repositório, parseia arquivos e persiste no grafo."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from eizo.graph.store import GraphStore
from eizo.parser.base import BaseParser
from eizo.parser.python import PythonParser
from eizo.parser.typescript import TypeScriptParser

console = Console()

# Diretórios e arquivos a ignorar
IGNORE_DIRS: set[str] = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".eggs", "dist", "build", ".egg-info",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".eizo",  # nosso próprio banco
}

IGNORE_FILES: set[str] = {
    ".DS_Store", "*.pyc", "*.pyo", "*.so", "*.dll", "*.dylib",
}


def _should_ignore(path: Path) -> bool:
    """Verifica se o caminho deve ser ignorado."""
    for part in path.parts:
        if part in IGNORE_DIRS:
            return True
    if path.name.startswith("."):
        return True
    return path.suffix in {".pyc", ".pyo", ".so", ".dll", ".dylib", ".egg-info"}


def _get_parsers() -> list[BaseParser]:
    """Retorna lista de parsers disponíveis."""
    parsers: list[BaseParser] = []
    try:
        parsers.append(PythonParser())
    except RuntimeError as e:
        console.print(f"[yellow]⚠ Python parser não disponível: {e}[/yellow]")
    try:
        parsers.append(TypeScriptParser())
    except RuntimeError as e:
        console.print(f"[yellow]⚠ TypeScript parser não disponível: {e}[/yellow]")
    return parsers


def _get_parser_for_file(file_path: Path, parsers: list[BaseParser]) -> BaseParser | None:
    """Encontra o parser adequado para um arquivo."""
    for parser in parsers:
        if parser.should_parse(file_path):
            return parser
    return None


def index_repository(
    repo_path: Path | str,
    store: GraphStore | None = None,
) -> GraphStore:
    """Indexa um repositório inteiro no grafo de conhecimento.

    Args:
        repo_path: Caminho do repositório.
        store: GraphStore existente (opcional). Se None, cria um novo.

    Returns:
        GraphStore populado.
    """
    repo_path = Path(repo_path).resolve()
    if not repo_path.is_dir():
        msg = f"Caminho não é um diretório válido: {repo_path}"
        raise NotADirectoryError(msg)

    if store is None:
        store = GraphStore(repo_path)

    parsers = _get_parsers()
    if not parsers:
        console.print("[red]✗ Nenhum parser disponível. Instale tree-sitter-python e/ou tree-sitter-typescript.[/red]")
        return store

    # Colete todos os arquivos parseáveis
    files: list[Path] = []
    for ext in {e for p in parsers for e in p.extensions}:
        files.extend(repo_path.rglob(f"*{ext}"))

    # Filtra ignorados
    files = [f for f in files if not _should_ignore(f)]

    if not files:
        console.print("[yellow]⚠ Nenhum arquivo parseável encontrado.[/yellow]")
        return store

    console.print(f"[bold]Indexando {len(files)} arquivos em {repo_path}...[/bold]")

    # Progresso
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )

    total_nodes = 0
    total_edges = 0
    errors: list[tuple[Path, str]] = []

    with progress:
        task = progress.add_task("[cyan]Parseando arquivos...", total=len(files))

        for file_path in files:
            parser = _get_parser_for_file(file_path, parsers)
            if parser is None:
                progress.advance(task)
                continue

            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                nodes, edges = parser.parse_file(file_path, source)

                # Remove nós antigos do arquivo e reinsere
                store.delete_nodes_by_file(str(file_path))
                store.upsert_nodes(nodes)
                store.upsert_edges(edges)

                total_nodes += len(nodes)
                total_edges += len(edges)

            except Exception as e:
                errors.append((file_path, str(e)))

            progress.advance(task)

    # Resumo
    stats = store.get_stats()
    console.print("\n[bold green]✓ Indexação concluída![/bold green]")
    console.print(f"  Arquivos: {stats.total_files}")
    console.print(f"  Nós: {stats.total_nodes}")
    console.print(f"  Arestas: {stats.total_edges}")
    console.print(f"  Linguagens: {', '.join(stats.by_language.keys())}")
    console.print(f"  Tamanho do banco: {stats.db_size_bytes / 1024:.1f} KB")

    if errors:
        console.print(f"\n[yellow]⚠ {len(errors)} erro(s) durante indexação:[/yellow]")
        for file_path, error in errors[:5]:
            console.print(f"  [red]{file_path}: {error}[/red]")
        if len(errors) > 5:
            console.print(f"  ... e mais {len(errors) - 5} erro(s)")

    return store
