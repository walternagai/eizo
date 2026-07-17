"""Indexer — orquestrador que percorre repositório, parseia arquivos e persiste no grafo."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
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


def _file_content_hash(source: str) -> str:
    """Calcula hash SHA-256 do conteúdo do arquivo (primeiros 16 hex chars)."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


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
    force: bool = False,
) -> GraphStore:
    """Indexa um repositório inteiro no grafo de conhecimento.

    Usa indexação incremental: arquivos cujo conteúdo (hash) não mudou desde a
    última indexação são pulados. Use `force=True` para reindexar tudo.

    Args:
        repo_path: Caminho do repositório.
        store: GraphStore existente (opcional). Se None, cria um novo.
        force: Se True, reindexa todos os arquivos ignorando o cache.

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

    # Colete todos os arquivos parseáveis. Poda IGNORE_DIRS durante o walk
    # (via os.walk, que permite modificar dirnames in-place) em vez de
    # enumerar a árvore inteira e filtrar depois — importante para repos
    # JS/TS onde node_modules pode ter dezenas de milhares de arquivos.
    extensions = {e for p in parsers for e in p.extensions}
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for filename in filenames:
            if Path(filename).suffix in extensions:
                files.append(Path(dirpath) / filename)

    # Filtra ignorados (arquivos ocultos, extensões binárias etc. — a poda
    # acima já cobre os diretórios em IGNORE_DIRS, mas mantemos o filtro
    # para os demais critérios de _should_ignore).
    files = [f for f in files if not _should_ignore(f)]

    if not files:
        console.print("[yellow]⚠ Nenhum arquivo parseável encontrado.[/yellow]")
        return store

    # Filtra arquivos inalterados (indexação incremental)
    files_to_index: list[Path] = []
    skipped = 0
    for f in files:
        if force:
            files_to_index.append(f)
            continue
        try:
            source = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        content_hash = _file_content_hash(source)
        if store.is_file_unchanged(str(f), content_hash):
            skipped += 1
        else:
            files_to_index.append(f)

    if not files_to_index:
        console.print(f"[green]✓ {len(files)} arquivo(s) já indexado(s), nada a fazer.[/green]")
        console.print("  Use --rebuild para forçar reindexação completa.")
        return store

    action = "Reindexando" if force else "Indexando"
    console.print(f"[bold]{action} {len(files_to_index)} arquivo(s) em {repo_path}...[/bold]")
    if skipped > 0:
        console.print(f"[dim]  {skipped} arquivo(s) inalterado(s) pulado(s)[/dim]")

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
        task = progress.add_task("[cyan]Parseando arquivos...", total=len(files_to_index))

        for file_path in files_to_index:
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

                # Atualiza índice incremental
                content_hash = _file_content_hash(source)
                mtime = file_path.stat().st_mtime
                indexed_at = dt.datetime.now(dt.timezone.utc).isoformat()
                store.upsert_file_index(str(file_path), content_hash, mtime, indexed_at)

                total_nodes += len(nodes)
                total_edges += len(edges)

            except Exception as e:
                errors.append((file_path, str(e)))

            progress.advance(task)

    # Resumo
    stats = store.get_stats()
    console.print("\n[bold green]✓ Indexação concluída![/bold green]")
    console.print(f"  Arquivos indexados: {len(files_to_index)}")
    console.print(f"  Arquivos pulados: {skipped}")
    console.print(f"  Total no grafo: {stats.total_files} arquivos")
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
