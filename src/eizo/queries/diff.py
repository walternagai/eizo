"""`eizo diff <ref>` — compara o working tree contra um ref git, símbolo a símbolo.

Não mantém um segundo grafo indexado nem reindexa nada: para cada arquivo que
mudou entre `ref` e o working tree (`git diff --name-only`), reparseia as
duas versões — disco atual e `git show ref:path` — com o mesmo parser usado
na indexação, e compara os conjuntos de definições (nome, kind). Cobre o caso
mais comum ("o que meu branch mudou em relação a main"); não cobre diff entre
dois refs arbitrários nem impacto histórico de símbolos removidos, que
exigiriam um segundo grafo completo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from eizo.graph.models import DEFINITION_KINDS
from eizo.indexer import _get_parser_for_file, _get_parsers


def _run_git_show(repo_path: Path, ref: str, rel_path: str) -> str | None:
    """Conteúdo de `rel_path` em `ref`, ou None se o arquivo não existia lá
    (falha esperada — não é erro, é o sinal de arquivo novo)."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show", f"{ref}:{rel_path}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _changed_files(repo_path: Path, ref: str) -> list[str]:
    """Arquivos que mudaram entre `ref` e o working tree (paths relativos à raiz do git).

    Diferente de `_run_git_show`, falha aqui É erro real — ref inexistente,
    ou `repo_path` fora de um repositório git — e deve interromper o diff,
    não ser tratada como "nenhuma mudança".
    """
    result = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--name-only", ref],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        msg = result.stderr.strip() or f"git diff falhou para o ref '{ref}'"
        raise RuntimeError(msg)
    return [line for line in result.stdout.splitlines() if line]


def _symbol_set(parsers: list[Any], file_path: Path, source: str | None) -> set[tuple[str, str]]:
    """(nome, kind) de cada definição (function/method/class) em `source`.

    `source=None` representa "arquivo não existe nesta versão" — conjunto vazio.
    """
    if source is None:
        return set()
    parser = _get_parser_for_file(file_path, parsers)
    if parser is None:
        return set()
    nodes, _edges = parser.parse_file(file_path, source)
    return {(n.name, n.kind) for n in nodes if n.kind in DEFINITION_KINDS}


def diff_against_ref(repo_path: Path | str, ref: str) -> dict[str, Any]:
    """Compara os símbolos do working tree contra `ref`, arquivo por arquivo.

    Args:
        repo_path: Raiz do repositório (também a raiz git usada nos comandos).
        ref: Ref git para comparar (branch, tag, commit — ex: 'main').

    Returns:
        Dict com 'ref' e 'files': lista de entradas por arquivo alterado com
        definições adicionadas/removidas, cada uma com:
        - "file": path relativo.
        - "status": "added" (novo), "removed" (apagado), ou "modified".
        - "added"/"removed": listas de [nome, kind] — símbolos que apareceram
          ou sumiram naquele arquivo entre `ref` e o working tree.

        Arquivos sem parser disponível (extensão não suportada) são
        ignorados. Arquivos modificados sem mudança de símbolos (ex: só
        corpo de função) não aparecem — o diff é sobre a superfície de
        símbolos, não sobre conteúdo linha a linha.

    Raises:
        RuntimeError: `repo_path` não é um repositório git, ou `ref` não existe.
    """
    repo_path = Path(repo_path).resolve()
    changed = _changed_files(repo_path, ref)
    parsers = _get_parsers()
    extensions = {e for p in parsers for e in p.extensions}

    results: list[dict[str, Any]] = []
    for rel_path in changed:
        if Path(rel_path).suffix not in extensions:
            continue

        abs_path = repo_path / rel_path
        current_source = abs_path.read_text(encoding="utf-8", errors="replace") if abs_path.is_file() else None
        ref_source = _run_git_show(repo_path, ref, rel_path)

        current_symbols = _symbol_set(parsers, abs_path, current_source)
        ref_symbols = _symbol_set(parsers, abs_path, ref_source)

        added = sorted(current_symbols - ref_symbols)
        removed = sorted(ref_symbols - current_symbols)

        if current_source is None:
            status = "removed"
        elif ref_source is None:
            status = "added"
        else:
            status = "modified"

        if status in ("added", "removed") or added or removed:
            results.append({
                "file": rel_path,
                "status": status,
                "added": [list(s) for s in added],
                "removed": [list(s) for s in removed],
            })

    return {"ref": ref, "files": results}
