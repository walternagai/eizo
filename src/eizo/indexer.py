"""Indexer — orquestrador que percorre repositório, parseia arquivos e persiste no grafo."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
from pathlib import Path

import pathspec
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from eizo.graph.store import GraphStore
from eizo.parser.base import BaseParser
from eizo.parser.go import GoParser
from eizo.parser.python import PythonParser
from eizo.parser.rust import RustParser
from eizo.parser.typescript import TypeScriptParser

console = Console()
logger = logging.getLogger("eizo")

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


def _load_ignore_spec(repo_path: Path) -> pathspec.PathSpec[pathspec.pattern.Pattern]:
    """Carrega os padrões de `.gitignore` e `.eizoignore` da raiz do repositório.

    Ambos usam a sintaxe gitignore (via `pathspec`) e são combinados num único
    spec — `.eizoignore` serve para exclusões específicas do eizo além do que
    já está no `.gitignore` (ex: manter um vendor/ versionado, mas não indexá-lo).
    Só a raiz é lida; `.gitignore` aninhados em subdiretórios não são
    combinados, ao contrário do git.
    """
    lines: list[str] = []
    for name in (".gitignore", ".eizoignore"):
        candidate = repo_path / name
        if candidate.is_file():
            lines.extend(candidate.read_text(encoding="utf-8", errors="replace").splitlines())
    return pathspec.PathSpec.from_lines("gitignore", lines)


def _get_parsers() -> list[BaseParser]:
    """Retorna lista de parsers disponíveis."""
    parsers: list[BaseParser] = []
    try:
        parsers.append(PythonParser())
        logger.debug("Python parser inicializado")
    except RuntimeError as e:
        logger.warning("Python parser não disponível: %s", e)
        console.print(f"[yellow]⚠ Python parser não disponível: {e}[/yellow]")
    try:
        parsers.append(TypeScriptParser())
        logger.debug("TypeScript parser inicializado")
    except RuntimeError as e:
        logger.warning("TypeScript parser não disponível: %s", e)
        console.print(f"[yellow]⚠ TypeScript parser não disponível: {e}[/yellow]")
    try:
        parsers.append(GoParser())
        logger.debug("Go parser inicializado")
    except RuntimeError as e:
        logger.warning("Go parser não disponível: %s", e)
        console.print(f"[yellow]⚠ Go parser não disponível: {e}[/yellow]")
    try:
        parsers.append(RustParser())
        logger.debug("Rust parser inicializado")
    except RuntimeError as e:
        logger.warning("Rust parser não disponível: %s", e)
        console.print(f"[yellow]⚠ Rust parser não disponível: {e}[/yellow]")
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
    dry_run: bool = False,
    quiet: bool = False,
) -> list[Path] | GraphStore:
    """Indexa um repositório inteiro no grafo de conhecimento.

    Sincroniza o grafo com o disco, cobrindo os três casos:

    - **criado**: arquivo novo é parseado e inserido;
    - **modificado**: hash diferente do registrado — os nós antigos daquele
      arquivo são removidos e reinseridos;
    - **removido**: arquivo que saiu do disco tem seus nós apagados do grafo.

    Arquivos cujo hash não mudou são pulados. Use `force=True` para reparsear
    tudo ignorando o cache — note que `force` não é o que remove órfãos; a
    detecção de remoção é sempre feita.

    Args:
        repo_path: Caminho do repositório.
        store: GraphStore existente (opcional). Se None, cria um novo.
        force: Se True, reindexa todos os arquivos ignorando o cache.
        dry_run: Se True, apenas descobre e retorna a lista de arquivos que
            seriam indexados, sem persistir no banco.
        quiet: Se True, suprime mensagens de console (útil para saída JSON).

    Returns:
        GraphStore populado quando dry_run=False; lista de Path quando dry_run=True.
    """
    repo_path = Path(repo_path).resolve()
    if not repo_path.is_dir():
        msg = f"Caminho não é um diretório válido: {repo_path}"
        raise NotADirectoryError(msg)

    if store is None and not dry_run:
        store = GraphStore(repo_path)

    parsers = _get_parsers()
    if not parsers:
        if not quiet:
            console.print("[red]✗ Nenhum parser disponível.[/red]")
            console.print("  Instale tree-sitter-python e/ou tree-sitter-typescript.")
        if dry_run:
            return []
        return store  # type: ignore[return-value]

    # Colete todos os arquivos parseáveis. Poda IGNORE_DIRS e os padrões de
    # .gitignore/.eizoignore durante o walk (via os.walk, que permite
    # modificar dirnames in-place) em vez de enumerar a árvore inteira e
    # filtrar depois — importante para repos JS/TS onde node_modules pode
    # ter dezenas de milhares de arquivos.
    ignore_spec = _load_ignore_spec(repo_path)
    extensions = {e for p in parsers for e in p.extensions}
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_path):
        rel_dir = Path(dirpath).relative_to(repo_path)

        def _dir_ignored(name: str, rel_dir: Path = rel_dir) -> bool:
            rel = (rel_dir / name).as_posix() if str(rel_dir) != "." else name
            # match_file() só reconhece padrões "só-diretório" (ex: "dist/")
            # se o caminho testado também terminar em "/".
            return ignore_spec.match_file(rel + "/")

        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not _dir_ignored(d)]
        for filename in filenames:
            if Path(filename).suffix in extensions:
                files.append(Path(dirpath) / filename)

    # Filtra ignorados (arquivos ocultos, extensões binárias etc. — a poda
    # acima já cobre os diretórios em IGNORE_DIRS/.gitignore/.eizoignore,
    # mas mantemos o filtro para os demais critérios de _should_ignore).
    files = [f for f in files if not _should_ignore(f)]
    files = [f for f in files if not ignore_spec.match_file(f.relative_to(repo_path).as_posix())]

    # Arquivos que sumiram do disco desde a última indexação. Comparamos contra
    # `files` — tudo que o walk encontrou — e não contra a lista de arquivos a
    # reindexar, que exclui justamente os inalterados (que continuam existindo).
    # Precisa vir antes do early return abaixo: apagar o último arquivo do repo
    # deixa `files` vazio e ainda assim exige limpeza.
    removed_files: list[str] = []
    if store is not None and not dry_run:
        on_disk = {str(f) for f in files}
        for indexed in store.get_indexed_files():
            # O mesmo store pode ter indexado outra árvore antes; só considera
            # sumido o que estava sob a raiz que estamos varrendo agora.
            if not Path(indexed).is_relative_to(repo_path):
                continue
            if indexed not in on_disk:
                store.delete_nodes_by_file(indexed)
                store.delete_file_index(indexed)
                removed_files.append(indexed)
                logger.info("Removido do grafo (não está mais no disco): %s", indexed)

    if not files:
        if not quiet:
            if removed_files:
                console.print(f"[green]✓ {len(removed_files)} arquivo(s) removido(s) do grafo.[/green]")
            console.print("[yellow]⚠ Nenhum arquivo parseável encontrado.[/yellow]")
        if dry_run:
            return []
        return store  # type: ignore[return-value]

    # Filtra arquivos inalterados (indexação incremental)
    files_to_index: list[Path] = []
    skipped = 0
    for f in files:
        if force:
            files_to_index.append(f)
            continue
        if dry_run:
            # Em dry-run não há cache; assume todos como candidatos.
            files_to_index.append(f)
            continue
        try:
            source = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        content_hash = _file_content_hash(source)
        if store is not None and store.is_file_unchanged(str(f), content_hash):
            skipped += 1
        else:
            files_to_index.append(f)

    if dry_run:
        logger.info("Dry-run: %d arquivo(s) candidatos em %s", len(files_to_index), repo_path)
        return files_to_index

    if not files_to_index:
        if not quiet:
            if removed_files:
                console.print(f"[green]✓ {len(removed_files)} arquivo(s) removido(s) do grafo.[/green]")
            console.print(f"[green]✓ {len(files)} arquivo(s) já indexado(s), nada a fazer.[/green]")
            console.print("  Use --rebuild para forçar reindexação completa.")
        return store  # type: ignore[return-value]

    action = "Reindexando" if force else "Indexando"
    if not quiet:
        console.print(f"[bold]{action} {len(files_to_index)} arquivo(s) em {repo_path}...[/bold]")
    logger.info("%s %d arquivo(s) em %s", action, len(files_to_index), repo_path)
    if skipped > 0 and not quiet:
        console.print(f"[dim]  {skipped} arquivo(s) inalterado(s) pulado(s)[/dim]")
        logger.info("%d arquivo(s) inalterado(s) pulado(s)", skipped)

    # Progresso
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        disable=quiet,
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

            logger.debug("Parseando %s", file_path)
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                nodes, edges = parser.parse_file(file_path, source)

                # Remove nós antigos do arquivo e reinsere
                if store is not None:
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
                logger.warning("Erro ao parsear %s: %s", file_path, e)
                errors.append((file_path, str(e)))

            progress.advance(task)

    # Resumo
    stats = store.get_stats() if store is not None else None
    if not quiet:
        console.print("\n[bold green]✓ Indexação concluída![/bold green]")
        console.print(f"  Arquivos indexados: {len(files_to_index)}")
        console.print(f"  Arquivos pulados: {skipped}")
        if removed_files:
            console.print(f"  Arquivos removidos: {len(removed_files)}")
        if stats:
            console.print(f"  Total no grafo: {stats.total_files} arquivos")
            console.print(f"  Nós: {stats.total_nodes}")
            console.print(f"  Arestas: {stats.total_edges}")
            console.print(f"  Linguagens: {', '.join(stats.by_language.keys())}")
            console.print(f"  Tamanho do banco: {stats.db_size_bytes / 1024:.1f} KB")
    logger.info(
        "Indexação concluída: %d arquivos, %d nós, %d arestas, %d removidos",
        len(files_to_index), total_nodes, total_edges, len(removed_files),
    )

    if errors and not quiet:
        console.print(f"\n[yellow]⚠ {len(errors)} erro(s) durante indexação:[/yellow]")
        for file_path, error in errors[:5]:
            console.print(f"  [red]{file_path}: {error}[/red]")
        if len(errors) > 5:
            console.print(f"  ... e mais {len(errors) - 5} erro(s)")

    return store  # type: ignore[return-value]
