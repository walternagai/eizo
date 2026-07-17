"""Schema SQLite e migrações para o grafo de conhecimento."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

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

-- Tabela de indexação incremental: rastreia hash e mtime por arquivo.
CREATE TABLE IF NOT EXISTS file_index (
    file_path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    mtime REAL NOT NULL,
    indexed_at TEXT NOT NULL
);

-- Tabela virtual FTS5 para busca full-text sobre nome + docstring + code_snippet.
-- Tabela FTS5 padrão (guarda próprio conteúdo): permite INSERT/DELETE direto.
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    node_id UNINDEXED,
    name,
    docstring,
    code_snippet
);

CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_language ON nodes(language);
CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
CREATE INDEX IF NOT EXISTS idx_edges_source_kind ON edges(source_id, kind);
CREATE INDEX IF NOT EXISTS idx_file_index_path ON file_index(file_path);
"""

# Migrações incrementais (v1 → v2). Cada entrada adiciona o que faltava na
# versão anterior. Rodam com "CREATE TABLE/VIRTUAL TABLE IF NOT EXISTS",
# então são idempotentes.
MIGRATION_V1_TO_V2 = """
CREATE TABLE IF NOT EXISTS file_index (
    file_path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    mtime REAL NOT NULL,
    indexed_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    node_id UNINDEXED,
    name,
    docstring,
    code_snippet
);

CREATE INDEX IF NOT EXISTS idx_file_index_path ON file_index(file_path);
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


def migrate_db(conn: sqlite3.Connection) -> None:
    """Aplica migrações incrementais baseadas na versão do schema registrada.

    DBs já existentes (v1) recebem as migrações para v2. Novos DBs já nascem na
    versão mais recente via `init_db`, então esta função é no-op para eles.
    """
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        return  # DB novo ainda sem meta; init_db cuidará.

    current = int(row[0])

    if current < 2:
        conn.executescript(MIGRATION_V1_TO_V2)
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
    # Sem isso, um segundo processo escrevendo concorrentemente (ex: `eizo mcp`
    # servindo enquanto `eizo init` reindexa) recebe "database is locked"
    # imediatamente em vez de esperar o lock liberar.
    conn.execute("PRAGMA busy_timeout=5000")

    # Inicializa schema se tabelas não existirem
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'")
    if cursor.fetchone() is None:
        init_db(conn)
    else:
        # DB já existe — aplica migrações pendentes
        migrate_db(conn)

    return conn
