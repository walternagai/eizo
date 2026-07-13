"""Testes para graph/schema.py."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from eizo.graph.schema import ensure_db_dir, get_db_path, init_db, open_db


class TestSchema:
    """Testes para schema do banco SQLite."""

    def test_get_db_path_default(self) -> None:
        """get_db_path deve retornar .eizo/graph.db no diretório atual."""
        path = get_db_path()
        assert path.name == "graph.db"
        assert path.parent.name == ".eizo"

    def test_get_db_path_custom(self) -> None:
        """get_db_path com path customizado."""
        path = get_db_path(Path("/tmp/teste"))
        assert str(path) == "/tmp/teste/.eizo/graph.db"

    def test_ensure_db_dir(self, tmp_path: Path) -> None:
        """ensure_db_dir deve criar o diretório .eizo."""
        db_path = ensure_db_dir(tmp_path)
        assert db_path.parent.exists()
        assert db_path.parent.is_dir()

    def test_init_db_creates_tables(self, tmp_path: Path) -> None:
        """init_db deve criar todas as tabelas."""
        db_path = ensure_db_dir(tmp_path)
        conn = sqlite3.connect(str(db_path))
        init_db(conn)

        # Verifica tabelas
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "meta" in tables
        assert "nodes" in tables
        assert "edges" in tables

        conn.close()

    def test_init_db_schema_version(self, tmp_path: Path) -> None:
        """init_db deve registrar a versão do schema."""
        db_path = ensure_db_dir(tmp_path)
        conn = sqlite3.connect(str(db_path))
        init_db(conn)

        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        assert row is not None
        assert row[0] == "1"

        conn.close()

    def test_open_db_creates_schema(self, tmp_path: Path) -> None:
        """open_db deve criar schema se não existir."""
        db_path = ensure_db_dir(tmp_path)
        conn = open_db(db_path)

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'"
        )
        assert cursor.fetchone() is not None

        conn.close()

    def test_open_db_wal_mode(self, tmp_path: Path) -> None:
        """open_db deve ativar WAL mode."""
        db_path = ensure_db_dir(tmp_path)
        conn = open_db(db_path)

        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"

        conn.close()
