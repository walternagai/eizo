"""Testes para indexer.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.graph.store import GraphStore
from eizo.indexer import index_repository


class TestIndexer:
    """Testes para o indexador."""

    def test_index_repository(self, sample_python_repo: Path) -> None:
        """Indexa um repositório Python de exemplo."""
        store = index_repository(sample_python_repo)

        stats = store.get_stats()
        assert stats.total_nodes > 0
        assert stats.total_edges > 0
        assert stats.total_files >= 2
        assert "python" in stats.by_language

    def test_index_repository_twice(self, sample_python_repo: Path) -> None:
        """Indexar duas vezes não deve duplicar nós."""
        store = index_repository(sample_python_repo)
        stats1 = store.get_stats()

        store2 = index_repository(sample_python_repo, store)
        stats2 = store2.get_stats()

        # Deve manter os mesmos nós (upsert)
        assert stats2.total_nodes == stats1.total_nodes

    def test_index_repository_rebuild(self, sample_python_repo: Path) -> None:
        """Rebuild deve limpar e reindexar."""
        store = GraphStore(sample_python_repo)
        index_repository(sample_python_repo, store)
        stats_before = store.get_stats()

        store.clear_all()
        index_repository(sample_python_repo, store)
        stats_after = store.get_stats()

        assert stats_after.total_nodes == stats_before.total_nodes

    def test_index_repository_invalid_path(self) -> None:
        """Caminho inválido deve levantar erro."""
        with pytest.raises(NotADirectoryError):
            index_repository("/caminho/inexistente")

    def test_index_repository_empty_dir(self, tmp_path: Path) -> None:
        """Diretório vazio deve retornar grafo vazio."""
        store = index_repository(tmp_path)
        stats = store.get_stats()
        assert stats.total_nodes == 0
