"""Benchmark de indexação em escala (B12 — Sprint #8 Robustez).

Gera um repositório sintético com N arquivos Python pequenos e mede:
tempo de indexação, pico de memória (tracemalloc) e volume do grafo
(nós/arestas/arquivos/tamanho do banco).

Script standalone — NÃO roda no CI (o `make check` não o referencia).
Uso:

    python3 benchmarks/benchmark_index.py [--files 10000] [--out DIR]

O conteúdo gerado é fixo (sem aleatoriedade): resultados são comparáveis
entre execuções. O diretório do repositório sintético fica em
`benchmarks/.bench_repo/` por padrão (gitignored).
"""

from __future__ import annotations

import argparse
import shutil
import time
import tracemalloc
from pathlib import Path

from eizo.graph.store import GraphStore
from eizo.indexer import index_repository

REPO_DIR = Path(__file__).resolve().parent / ".bench_repo"

# Corpo fixo de cada arquivo gerado — 4 funções por arquivo, com chamadas
# reais entre elas para exercitar nós 'call' e arestas 'calls'/'contains'.
FILE_TEMPLATE = '''\
"""Módulo gerado para benchmark (B12)."""

from __future__ import annotations


def func_{n:04d}_0(value: int) -> int:
    """Função gerada {n:04d}-0."""
    return value * 2


def func_{n:04d}_1(value: int) -> int:
    """Função gerada {n:04d}-1."""
    return func_{n:04d}_0(value) + 1


def func_{n:04d}_2(value: int) -> int:
    """Função gerada {n:04d}-2."""
    return func_{n:04d}_1(value) - 1


def func_{n:04d}_3(value: int) -> int:
    """Função gerada {n:04d}-3."""
    return func_{n:04d}_2(value) * func_{n:04d}_0(value)
'''


def generate_repo(repo: Path, num_files: int) -> None:
    """Gera `num_files` arquivos Python pequenos no diretório `repo`."""
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    for i in range(num_files):
        (repo / f"module_{i:05d}.py").write_text(
            FILE_TEMPLATE.format(n=i), encoding="utf-8"
        )


def run_benchmark(num_files: int, repo: Path) -> dict[str, float | int]:
    """Indexa o repositório e coleta as métricas."""
    generate_repo(repo, num_files)

    tracemalloc.start()
    start = time.monotonic()
    store = index_repository(repo, quiet=True)
    elapsed = time.monotonic() - start
    _, peak_python = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert isinstance(store, GraphStore)
    stats = store.get_stats()
    store.close()

    return {
        "files": num_files,
        "elapsed_s": round(elapsed, 3),
        "peak_memory_mb": round(peak_python / (1024 * 1024), 1),
        "total_nodes": stats.total_nodes,
        "total_edges": stats.total_edges,
        "total_files": stats.total_files,
        "db_size_mb": round(stats.db_size_bytes / (1024 * 1024), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=10000, help="nº de arquivos sintéticos")
    parser.add_argument("--out", type=Path, default=REPO_DIR, help="dir do repo sintético")
    args = parser.parse_args()

    if args.files < 1:
        parser.error("--files deve ser >= 1")

    metrics = run_benchmark(args.files, args.out)
    print("Benchmark de indexação (B12)")
    print("=" * 40)
    print(f"arquivos            : {metrics['files']}")
    print(f"tempo de indexação  : {metrics['elapsed_s']} s")
    print(f"pico de memória     : {metrics['peak_memory_mb']} MB (tracemalloc)")
    print(f"nós                 : {metrics['total_nodes']}")
    print(f"arestas             : {metrics['total_edges']}")
    print(f"arquivos indexados  : {metrics['total_files']}")
    print(f"tamanho do banco    : {metrics['db_size_mb']} MB")


if __name__ == "__main__":
    main()
