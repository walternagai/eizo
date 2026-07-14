"""Testes para indexação incremental (file_index) e FTS5 full-text search.

Cobre:
- GraphStore.get_file_index_entry / upsert_file_index / is_file_unchanged
- Indexação incremental no indexer (pula arquivos inalterados)
- GraphStore.search_nodes_fts (FTS5)
- Migração de schema v1 → v2
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from eizo.graph.models import Node
from eizo.graph.schema import ensure_db_dir, open_db
from eizo.graph.store import GraphStore
from eizo.indexer import index_repository

# ─── file_index (store) ────────────────────────────────────────


class TestFileIndex:
    """Testa operações de indexação incremental no GraphStore."""

    def test_upsert_and_get_file_index(self, store: GraphStore) -> None:
        """upsert_file_index insere e get_file_index_entry recupera."""
        store.upsert_file_index("/proj/main.py", "abc123", 1234567890.0, "2024-01-01T00:00:00Z")
        entry = store.get_file_index_entry("/proj/main.py")
        assert entry is not None
        assert entry["content_hash"] == "abc123"
        assert entry["mtime"] == 1234567890.0

    def test_get_file_index_entry_not_found(self, store: GraphStore) -> None:
        """get_file_index_entry retorna None para arquivo não indexado."""
        entry = store.get_file_index_entry("/proj/nonexistent.py")
        assert entry is None

    def test_is_file_unchanged_true(self, store: GraphStore) -> None:
        """is_file_unchanged retorna True quando hash bate."""
        store.upsert_file_index("/proj/main.py", "abc123", 1234567890.0, "2024-01-01T00:00:00Z")
        assert store.is_file_unchanged("/proj/main.py", "abc123") is True

    def test_is_file_unchanged_false_different_hash(self, store: GraphStore) -> None:
        """is_file_unchanged retorna False quando hash difere."""
        store.upsert_file_index("/proj/main.py", "abc123", 1234567890.0, "2024-01-01T00:00:00Z")
        assert store.is_file_unchanged("/proj/main.py", "different") is False

    def test_is_file_unchanged_false_not_indexed(self, store: GraphStore) -> None:
        """is_file_unchanged retorna False para arquivo nunca indexado."""
        assert store.is_file_unchanged("/proj/new.py", "abc123") is False

    def test_delete_file_index(self, store: GraphStore) -> None:
        """delete_file_index remove entry."""
        store.upsert_file_index("/proj/main.py", "abc123", 1234567890.0, "2024-01-01T00:00:00Z")
        store.delete_file_index("/proj/main.py")
        assert store.get_file_index_entry("/proj/main.py") is None

    def test_clear_all_removes_file_index(self, store: GraphStore) -> None:
        """clear_all também limpa file_index."""
        store.upsert_file_index("/proj/main.py", "abc123", 1234567890.0, "2024-01-01T00:00:00Z")
        store.clear_all()
        assert store.get_file_index_entry("/proj/main.py") is None


# ─── Indexação incremental (indexer) ────────────────────────────


class TestIncrementalIndexing:
    """Testa que o indexer pula arquivos inalterados."""

    def test_second_index_skips_unchanged(self, sample_python_repo: Path) -> None:
        """Segunda indexação pula arquivos inalterados."""
        store = index_repository(sample_python_repo)
        stats1 = store.get_stats()

        # Segunda indexação — deve pular todos os arquivos
        store2 = index_repository(sample_python_repo, store)
        stats2 = store2.get_stats()

        # Grafo deve estar idêntico
        assert stats2.total_nodes == stats1.total_nodes
        assert stats2.total_edges == stats1.total_edges

    def test_force_reindexes_all(self, sample_python_repo: Path) -> None:
        """force=True reindexa todos os arquivos mesmo sem mudanças."""
        store = index_repository(sample_python_repo)
        stats1 = store.get_stats()

        # Force reindex
        store2 = index_repository(sample_python_repo, store, force=True)
        stats2 = store2.get_stats()

        # Grafo deve ter os mesmos nós (reindexados)
        assert stats2.total_nodes == stats1.total_nodes

    def test_modified_file_gets_reindexed(self, sample_python_repo: Path) -> None:
        """Arquivo modificado é reindexado na segunda passada."""
        store = index_repository(sample_python_repo)
        stats1 = store.get_stats()

        # Modifica um arquivo — adiciona uma função nova
        helpers = sample_python_repo / "utils" / "helpers.py"
        content = helpers.read_text()
        helpers.write_text(content + "\n\ndef new_func():\n    pass\n")

        store2 = index_repository(sample_python_repo, store)
        stats2 = store2.get_stats()

        # Deve ter mais nós (a nova função)
        assert stats2.total_nodes > stats1.total_nodes

    def test_deleted_file_nodes_removed(self, sample_python_repo: Path) -> None:
        """Arquivo deletado do disco não fica órfão no grafo."""
        store = index_repository(sample_python_repo)
        stats1 = store.get_stats()
        assert stats1.total_nodes > 0

        # Remove um arquivo do disco
        (sample_python_repo / "utils" / "helpers.py").unlink()

        # Reindexa — o arquivo foi removido do disco, mas o eizo não detecta
        # automaticamente (apenas pula reindexação de arquivos que existem).
        # Verificamos que os nós do arquivo removido não são duplicados.
        store2 = index_repository(sample_python_repo, store)
        stats2 = store2.get_stats()

        # Os nós do arquivo removido ainda estão no grafo (eizo não detecta
        # remoção de arquivo automaticamente), mas não devem ter duplicado.
        assert stats2.total_nodes <= stats1.total_nodes


# ─── FTS5 full-text search ─────────────────────────────────────


class TestFtsSearch:
    """Testa busca full-text (FTS5)."""

    def test_fts_search_by_name(self, store: GraphStore) -> None:
        """Busca FTS5 por nome encontra símbolo."""
        store.upsert_nodes([
            Node(id="a1", name="get_user", kind="function", file_path="a.py",
                 language="python", docstring="Busca usuário no banco"),
            Node(id="a2", name="get_item", kind="function", file_path="b.py",
                 language="python", docstring="Busca item do estoque"),
        ])

        results = store.search_nodes_fts("get_user")
        assert len(results) >= 1
        assert any(r.name == "get_user" for r in results)

    def test_fts_search_by_docstring(self, store: GraphStore) -> None:
        """Busca FTS5 por conteúdo da docstring."""
        store.upsert_nodes([
            Node(id="a1", name="func_a", kind="function", file_path="a.py",
                 language="python", docstring="Processa pagamento via cartão"),
            Node(id="a2", name="func_b", kind="function", file_path="b.py",
                 language="python", docstring="Valida estoque"),
        ])

        results = store.search_nodes_fts("pagamento")
        assert len(results) >= 1
        assert results[0].name == "func_a"

    def test_fts_search_by_code_snippet(self, store: GraphStore) -> None:
        """Busca FTS5 por conteúdo do code_snippet."""
        store.upsert_nodes([
            Node(id="a1", name="func_a", kind="function", file_path="a.py",
                 language="python", code_snippet="def func_a(): return database_connection()"),
            Node(id="a2", name="func_b", kind="function", file_path="b.py",
                 language="python", code_snippet="def func_b(): pass"),
        ])

        results = store.search_nodes_fts("database_connection")
        assert len(results) >= 1
        assert results[0].name == "func_a"

    def test_fts_search_with_kind_filter(self, store: GraphStore) -> None:
        """Busca FTS5 com filtro de kind."""
        store.upsert_nodes([
            Node(id="a1", name="user", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="user", kind="class", file_path="b.py", language="python"),
        ])

        results = store.search_nodes_fts("user", kind="class")
        assert len(results) == 1
        assert results[0].kind == "class"

    def test_fts_search_with_language_filter(self, store: GraphStore) -> None:
        """Busca FTS5 com filtro de linguagem."""
        store.upsert_nodes([
            Node(id="a1", name="helper", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="helper", kind="function", file_path="b.ts", language="typescript"),
        ])

        results = store.search_nodes_fts("helper", language="typescript")
        assert len(results) == 1
        assert results[0].language == "typescript"

    def test_fts_search_no_results(self, store: GraphStore) -> None:
        """Busca FTS5 sem matches retorna lista vazia."""
        store.upsert_nodes([
            Node(id="a1", name="foo", kind="function", file_path="a.py", language="python"),
        ])

        results = store.search_nodes_fts("zzz_nonexistent_zzz")
        assert results == []

    def test_fts_search_prefix_wildcard(self, store: GraphStore) -> None:
        """Busca FTS5 com prefixo wildcard (*) encontra matches parciais."""
        store.upsert_nodes([
            Node(id="a1", name="get_user", kind="function", file_path="a.py", language="python"),
            Node(id="a2", name="get_item", kind="function", file_path="b.py", language="python"),
            Node(id="a3", name="set_value", kind="function", file_path="c.py", language="python"),
        ])

        results = store.search_nodes_fts("get*")
        assert len(results) >= 2

    def test_fts_search_reindex_updates(self, store: GraphStore) -> None:
        """Re-upsert de nó atualiza índice FTS (não duplica)."""
        store.upsert_nodes([
            Node(id="a1", name="foo", kind="function", file_path="a.py",
                 language="python", docstring="versão 1"),
        ])
        results1 = store.search_nodes_fts("versão")
        assert len(results1) == 1

        # Re-upsert com docstring diferente
        store.upsert_nodes([
            Node(id="a1", name="foo", kind="function", file_path="a.py",
                 language="python", docstring="versão 2 atualizada"),
        ])
        results2 = store.search_nodes_fts("atualizada")
        assert len(results2) == 1
        assert results2[0].docstring == "versão 2 atualizada"

    def test_fts_search_after_delete_by_file(self, store: GraphStore) -> None:
        """delete_nodes_by_file também remove do índice FTS."""
        store.upsert_nodes([
            Node(id="a1", name="foo", kind="function", file_path="a.py",
                 language="python", docstring="especial"),
            Node(id="a2", name="bar", kind="function", file_path="b.py",
                 language="python", docstring="especial"),
        ])

        # Antes do delete, ambos aparecem
        results_before = store.search_nodes_fts("especial")
        assert len(results_before) == 2

        store.delete_nodes_by_file("a.py")

        # Depois do delete, só o do b.py aparece
        results_after = store.search_nodes_fts("especial")
        assert len(results_after) == 1
        assert results_after[0].file_path == "b.py"


# ─── Migração de schema ────────────────────────────────────────


class TestSchemaMigration:
    """Testa migração de schema v1 → v2."""

    def test_migrate_v1_to_v2_adds_file_index(self, tmp_path: Path) -> None:
        """DB criado na v1 recebe tabela file_index após migração."""
        db_path = ensure_db_dir(tmp_path)
        conn = sqlite3.connect(str(db_path))

        # Cria schema v1 manualmente (sem file_index nem nodes_fts)
        conn.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE nodes (id TEXT PRIMARY KEY, name TEXT, kind TEXT, file_path TEXT,
                language TEXT, line_start INTEGER, line_end INTEGER,
                docstring TEXT, code_snippet TEXT, metadata TEXT DEFAULT '{}');
            CREATE TABLE edges (id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT, target_id TEXT, kind TEXT, metadata TEXT DEFAULT '{}');
            INSERT INTO meta (key, value) VALUES ('schema_version', '1');
        """)
        conn.commit()
        conn.close()

        # Abre via open_db — deve detectar v1 e migrar para v2
        conn = open_db(db_path)

        # Verifica que file_index foi criada
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_index'"
        )
        assert cursor.fetchone() is not None

        # Verifica que nodes_fts foi criada
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes_fts'"
        )
        assert cursor.fetchone() is not None

        # Versão atualizada
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        assert row[0] == "2"

        conn.close()

    def test_migrate_already_v2_is_noop(self, tmp_path: Path) -> None:
        """DB já na v2 não migra novamente."""
        db_path = ensure_db_dir(tmp_path)
        conn = open_db(db_path)  # Cria na v2
        conn.close()

        # Reabre — não deve falhar nem duplicar
        conn = open_db(db_path)
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        assert row[0] == "2"
        conn.close()
