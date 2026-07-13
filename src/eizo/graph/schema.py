"""Schema SQLite e migrações para o grafo de conhecimento."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    docstring TEXT,
    code_snippet TEXT,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    UNIQUE(source_id, target_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_language ON nodes(language);
CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
CREATE INDEX IF NOT EXISTS idx_edges_source_kind ON edges(source_id, kind);
"""


def get_db_path(path: Path | None = None) -> Path:
    """Retorna o caminho do banco SQLite.

    Se path for None, usa o diretório atual.
    """
    base = path or Path.cwd()
    return base / ".eizo" / "graph.db"


def ensure_db_dir(path: Path | None) -> Path:
    """Garante que o diretório do banco existe."""
    db_path = get_db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def init_db(conn: sqlite3.Connection) -> None:
    """Inicializa o schema do banco de dados."""
    conn.executescript(SCHEMA_SQL)

    # Registra versão do schema
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.commit()


def open_db(path: Path) -> sqlite3.Connection:
    """Abre conexão com o banco SQLite e garante schema atualizado."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Inicializa schema se tabelas não existirem
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'")
    if cursor.fetchone() is None:
        init_db(conn)

    return conn
