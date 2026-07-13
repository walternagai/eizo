"""GraphStore — CRUD no SQLite para o grafo de conhecimento."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from eizo.graph.models import Edge, GraphStats, Node
from eizo.graph.schema import ensure_db_dir, open_db


class GraphStore:
    """Armazena e consulta o grafo de conhecimento em SQLite."""

    def __init__(self, path: Path | None = None) -> None:
        self.db_path = ensure_db_dir(path)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = open_db(self.db_path)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ─── Node operations ───────────────────────────────────────

    def upsert_node(self, node: Node) -> None:
        """Insere ou atualiza um nó no grafo."""
        self.conn.execute(
            """INSERT OR REPLACE INTO nodes
               (id, name, kind, file_path, language, line_start, line_end, docstring, code_snippet, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node.id,
                node.name,
                node.kind,
                node.file_path,
                node.language,
                node.line_start,
                node.line_end,
                node.docstring,
                node.code_snippet,
                json.dumps(node.metadata, default=str),
            ),
        )
        self.conn.commit()

    def upsert_nodes(self, nodes: list[Node]) -> None:
        """Insere ou atualiza múltiplos nós em lote."""
        data = [
            (
                n.id,
                n.name,
                n.kind,
                n.file_path,
                n.language,
                n.line_start,
                n.line_end,
                n.docstring,
                n.code_snippet,
                json.dumps(n.metadata, default=str),
            )
            for n in nodes
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO nodes
               (id, name, kind, file_path, language, line_start, line_end, docstring, code_snippet, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            data,
        )
        self.conn.commit()

    def get_node(self, node_id: str) -> Node | None:
        """Busca um nó pelo ID."""
        row = self.conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return self._row_to_node(row) if row else None

    def search_nodes(
        self,
        query: str,
        kind: str | None = None,
        language: str | None = None,
        limit: int = 50,
    ) -> list[Node]:
        """Busca nós por nome (LIKE)."""
        sql = "SELECT * FROM nodes WHERE name LIKE ?"
        params: list[Any] = [f"%{query}%"]

        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if language:
            sql += " AND language = ?"
            params.append(language)

        sql += " LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_nodes_by_file(self, file_path: str) -> list[Node]:
        """Retorna todos os nós de um arquivo."""
        rows = self.conn.execute(
            "SELECT * FROM nodes WHERE file_path = ? ORDER BY line_start",
            (file_path,),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def delete_nodes_by_file(self, file_path: str) -> None:
        """Remove todos os nós e arestas de um arquivo."""
        self.conn.execute(
            "DELETE FROM edges WHERE source_id IN (SELECT id FROM nodes WHERE file_path = ?)",
            (file_path,),
        )
        self.conn.execute(
            "DELETE FROM edges WHERE target_id IN (SELECT id FROM nodes WHERE file_path = ?)",
            (file_path,),
        )
        self.conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
        self.conn.commit()

    def clear_all(self) -> None:
        """Remove todos os nós e arestas."""
        self.conn.execute("DELETE FROM edges")
        self.conn.execute("DELETE FROM nodes")
        self.conn.commit()

    # ─── Edge operations ────────────────────────────────────────

    def upsert_edge(self, edge: Edge) -> None:
        """Insere ou atualiza uma aresta."""
        self.conn.execute(
            """INSERT OR REPLACE INTO edges (source_id, target_id, kind, metadata)
               VALUES (?, ?, ?, ?)""",
            (
                edge.source_id,
                edge.target_id,
                edge.kind,
                json.dumps(edge.metadata, default=str),
            ),
        )
        self.conn.commit()

    def upsert_edges(self, edges: list[Edge]) -> None:
        """Insere ou atualiza múltiplas arestas em lote."""
        data = [
            (
                e.source_id,
                e.target_id,
                e.kind,
                json.dumps(e.metadata, default=str),
            )
            for e in edges
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO edges (source_id, target_id, kind, metadata)
               VALUES (?, ?, ?, ?)""",
            data,
        )
        self.conn.commit()

    def get_outgoing_edges(self, node_id: str, kind: str | None = None) -> list[Edge]:
        """Retorna arestas que saem de um nó."""
        sql = "SELECT * FROM edges WHERE source_id = ?"
        params: list[Any] = [node_id]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def get_incoming_edges(self, node_id: str, kind: str | None = None) -> list[Edge]:
        """Retorna arestas que chegam em um nó."""
        sql = "SELECT * FROM edges WHERE target_id = ?"
        params: list[Any] = [node_id]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_edge(r) for r in rows]

    # ─── Stats ─────────────────────────────────────────────────

    def get_stats(self) -> GraphStats:
        """Retorna estatísticas do grafo."""
        stats = GraphStats()

        row = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
        stats.total_nodes = row[0] if row else 0

        row = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        stats.total_edges = row[0] if row else 0

        rows = self.conn.execute(
            "SELECT language, COUNT(*) as cnt FROM nodes GROUP BY language ORDER BY cnt DESC"
        ).fetchall()
        stats.by_language = {r["language"]: r["cnt"] for r in rows}

        rows = self.conn.execute(
            "SELECT kind, COUNT(*) as cnt FROM nodes GROUP BY kind ORDER BY cnt DESC"
        ).fetchall()
        stats.by_kind = {r["kind"]: r["cnt"] for r in rows}

        rows = self.conn.execute(
            "SELECT kind, COUNT(*) as cnt FROM edges GROUP BY kind ORDER BY cnt DESC"
        ).fetchall()
        stats.by_edge_kind = {r["kind"]: r["cnt"] for r in rows}

        row = self.conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM nodes"
        ).fetchone()
        stats.total_files = row[0] if row else 0

        stats.db_size_bytes = self.db_path.stat().st_size

        return stats

    # ─── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> Node:
        return Node(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            file_path=row["file_path"],
            language=row["language"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            docstring=row["docstring"],
            code_snippet=row["code_snippet"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> Edge:
        return Edge(
            source_id=row["source_id"],
            target_id=row["target_id"],
            kind=row["kind"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
