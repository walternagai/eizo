"""GraphStore — CRUD no SQLite para o grafo de conhecimento."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from eizo.graph.models import DEFINITION_KINDS, Edge, GraphStats, Node
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
        # Sincroniza índice FTS5: remove entradas antigas e reinsere.
        if nodes:
            self.conn.executemany(
                "DELETE FROM nodes_fts WHERE node_id = ?", [(n.id,) for n in nodes]
            )
            fts_data = [
                (n.id, n.name or "", n.docstring or "", n.code_snippet or "")
                for n in nodes
            ]
            self.conn.executemany(
                "INSERT INTO nodes_fts (node_id, name, docstring, code_snippet) VALUES (?, ?, ?, ?)",
                fts_data,
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
        """Busca nós por nome (LIKE), priorizando match exato e definições."""
        sql = "SELECT * FROM nodes WHERE name LIKE ?"
        params: list[Any] = [f"%{query}%"]

        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if language:
            sql += " AND language = ?"
            params.append(language)

        # Fix A: match exato primeiro, depois definições (function/method/class)
        # antes de call sites (call/import/file)
        sql += (
            " ORDER BY"
            " CASE WHEN name = ? THEN 0 ELSE 1 END,"
            " CASE kind"
            " WHEN 'function' THEN 0"
            " WHEN 'method' THEN 1"
            " WHEN 'class' THEN 2"
            " WHEN 'call' THEN 3"
            " WHEN 'import' THEN 4"
            " WHEN 'file' THEN 5"
            " ELSE 6 END,"
            " name"
        )
        params.append(query)

        sql += " LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_nodes_by_name(
        self,
        name: str,
        kind: str | None = None,
    ) -> list[Node]:
        """Busca nós por nome exato (opcionalmente filtrados por kind)."""
        sql = "SELECT * FROM nodes WHERE name = ?"
        params: list[Any] = [name]

        if kind:
            sql += " AND kind = ?"
            params.append(kind)

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
        # Coleta IDs antes de deletar para limpar o FTS
        rows = self.conn.execute(
            "SELECT id FROM nodes WHERE file_path = ?", (file_path,)
        ).fetchall()
        node_ids = [r["id"] for r in rows]

        self.conn.execute(
            "DELETE FROM edges WHERE source_id IN (SELECT id FROM nodes WHERE file_path = ?)",
            (file_path,),
        )
        self.conn.execute(
            "DELETE FROM edges WHERE target_id IN (SELECT id FROM nodes WHERE file_path = ?)",
            (file_path,),
        )
        self.conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))

        # Limpa índice FTS5
        if node_ids:
            self.conn.executemany(
                "DELETE FROM nodes_fts WHERE node_id = ?", [(nid,) for nid in node_ids]
            )

        self.conn.commit()

    def search_nodes_fts(
        self,
        query: str,
        kind: str | None = None,
        language: str | None = None,
        limit: int = 50,
    ) -> list[Node]:
        """Busca full-text (FTS5) sobre nome + docstring + code_snippet.

        Suporta sintaxe FTS5: prefixo com '*', AND/OR, frases com aspas.
        Retorna nós ordenados por relevância (rank FTS5).
        """
        # Sanitiza query para FTS5 — envolve em aspas se não for query avançada
        fts_query = query if any(op in query for op in ('"', "*", "AND", "OR", "NOT")) else f'"{query}"'

        sql = (
            "SELECT n.* FROM nodes_fts f "
            "JOIN nodes n ON n.id = f.node_id "
            "WHERE nodes_fts MATCH ?"
        )
        params: list[Any] = [fts_query]

        if kind:
            sql += " AND n.kind = ?"
            params.append(kind)
        if language:
            sql += " AND n.language = ?"
            params.append(language)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def clear_all(self) -> None:
        """Remove todos os nós e arestas."""
        self.conn.execute("DELETE FROM edges")
        self.conn.execute("DELETE FROM nodes")
        self.conn.execute("DELETE FROM nodes_fts")
        self.conn.execute("DELETE FROM file_index")
        self.conn.commit()

    # ─── File index (incremental) ───────────────────────────────

    def get_file_index_entry(self, file_path: str) -> dict[str, Any] | None:
        """Retorna entry de indexação incremental para um arquivo, ou None."""
        row = self.conn.execute(
            "SELECT content_hash, mtime, indexed_at FROM file_index WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if row is None:
            return None
        return {"content_hash": row["content_hash"], "mtime": row["mtime"], "indexed_at": row["indexed_at"]}

    def upsert_file_index(self, file_path: str, content_hash: str, mtime: float, indexed_at: str) -> None:
        """Insere ou atualiza entry de indexação incremental."""
        self.conn.execute(
            """INSERT OR REPLACE INTO file_index (file_path, content_hash, mtime, indexed_at)
               VALUES (?, ?, ?, ?)""",
            (file_path, content_hash, mtime, indexed_at),
        )
        self.conn.commit()

    def delete_file_index(self, file_path: str) -> None:
        """Remove entry de indexação incremental para um arquivo."""
        self.conn.execute("DELETE FROM file_index WHERE file_path = ?", (file_path,))
        self.conn.commit()

    def is_file_unchanged(self, file_path: str, content_hash: str) -> bool:
        """Verifica se o arquivo já está indexado com o mesmo hash (não precisa reindexar)."""
        entry = self.get_file_index_entry(file_path)
        return entry is not None and entry["content_hash"] == content_hash

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

    # ─── Resolução de call sites ──────────────────────────────────
    #
    # O parser cria arestas caller → call_site (nó kind='call') em vez de
    # caller → definição para chamadas. Estes helpers resolvem esse padrão
    # de forma centralizada, para não reimplementar a mesma lógica em cada
    # query module (trace, impact, analysis).

    def resolve_call_to_definition(self, call_node: Node) -> Node:
        """Dado um nó kind='call', tenta achar a definição com mesmo nome.

        Retorna o próprio call_node se não houver definição correspondente
        (preserva informação — ex: chamadas a símbolos externos ao repo).
        """
        for candidate in self.get_nodes_by_name(call_node.name):
            if candidate.kind in DEFINITION_KINDS:
                return candidate
        return call_node

    def get_real_references(self, node_id: str, node_name: str) -> list[tuple[Node, str]]:
        """Retorna (nó_referenciador, kind) para cada referência real a um nó.

        Arestas `contains` (arquivo/classe → membro) são puramente
        estruturais e não indicam uso, por isso são ignoradas. Resolve dois
        caminhos para achar referências reais:

        - Arestas `calls`/`imports`/`inherits` diretas para o nó.
        - Nós kind='call' com o mesmo nome (call sites), subindo via aresta
          `calls` até quem fez a chamada.

        Deduplica por (referrer.id, kind): o mesmo caller pode aparecer via
        ambos os caminhos de `calls`, mas não deve ser contado duas vezes.
        """
        seen: set[tuple[str, str]] = set()
        results: list[tuple[Node, str]] = []

        def _add(referrer: Node, kind: str) -> None:
            key = (referrer.id, kind)
            if key not in seen:
                seen.add(key)
                results.append((referrer, kind))

        for kind in ("calls", "imports", "inherits"):
            for edge in self.get_incoming_edges(node_id, kind=kind):
                referrer = self.get_node(edge.source_id)
                if referrer:
                    _add(referrer, kind)

        for call_site in self.get_nodes_by_name(node_name, kind="call"):
            if call_site.id == node_id:
                continue
            for edge in self.get_incoming_edges(call_site.id, kind="calls"):
                referrer = self.get_node(edge.source_id)
                if referrer:
                    _add(referrer, "calls")

        return results

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
