"""Exportação do grafo para formatos de visualização.

Suporta:
- DOT (Graphviz): para renderização com `dot -Tpng graph.dot -o graph.png`
- Mermaid: para renderização em GitHub, GitLab, Notion, etc.
- JSON: para importação em ferramentas de visualização
- HTML: grafo 3D interativo e navegável no browser (offline, self-contained)

Filtros opcionais: por kind, por linguagem, por arquivo (glob), limite de nós.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from eizo.graph.models import Edge, Node
from eizo.graph.store import GraphStore


def _fetch_nodes(
    store: GraphStore,
    kind: str | None = None,
    language: str | None = None,
    limit: int | None = None,
) -> list[Node]:
    """Busca nós com filtros opcionais."""
    sql = "SELECT * FROM nodes WHERE 1=1"
    params: list[Any] = []

    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if language:
        sql += " AND language = ?"
        params.append(language)
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    rows = store.conn.execute(sql, params).fetchall()
    return [store._row_to_node(r) for r in rows]


def _fetch_edges_for_nodes(store: GraphStore, node_ids: set[str]) -> list[Edge]:
    """Busca arestas onde ambos source e target estão no conjunto de nós."""
    if not node_ids:
        return []
    placeholders = ",".join("?" * len(node_ids))
    sql = f"""
        SELECT * FROM edges
        WHERE source_id IN ({placeholders})
          AND target_id IN ({placeholders})
    """
    params = list(node_ids) + list(node_ids)
    rows = store.conn.execute(sql, params).fetchall()
    return [store._row_to_edge(r) for r in rows]


def _sanitize_dot_id(node_id: str) -> str:
    """Sanitiza ID para DOT ( alphanumeric + underscore)."""
    return "n_" + node_id.replace("-", "_")


def export_dot(
    store: GraphStore,
    kind: str | None = None,
    language: str | None = None,
    limit: int | None = None,
    edge_kinds: frozenset[str] | None = None,
) -> str:
    """Exporta o grafo para formato Graphviz DOT.

    Args:
        store: GraphStore com o grafo.
        kind: Filtrar nós por tipo (function, class, method).
        language: Filtrar nós por linguagem.
        limit: Máximo de nós.
        edge_kinds: Filtrar arestas por tipo (calls, imports, inherits, contains).
            Se None, inclui todas.

    Returns:
        String no formato DOT.
    """
    nodes = _fetch_nodes(store, kind=kind, language=language, limit=limit)
    node_ids = {n.id for n in nodes}
    edges = _fetch_edges_for_nodes(store, node_ids)

    if edge_kinds:
        edges = [e for e in edges if e.kind in edge_kinds]

    lines: list[str] = []
    lines.append("digraph eizo {")
    lines.append("  rankdir=LR;")
    lines.append('  node [fontname="Arial", fontsize=10];')
    lines.append('  edge [fontname="Arial", fontsize=8];')
    lines.append("")

    # Nós
    lines.append("  // Nós")
    for n in nodes:
        dot_id = _sanitize_dot_id(n.id)
        label = n.name
        # Estilo por kind
        if n.kind == "class":
            shape = "box"
            color = "lightblue"
        elif n.kind == "function":
            shape = "ellipse"
            color = "lightgreen"
        elif n.kind == "method":
            shape = "ellipse"
            color = "lightyellow"
        else:
            shape = "ellipse"
            color = "white"
        lines.append(f'  {dot_id} [label="{label}", shape={shape}, style=filled, fillcolor={color}];')
    lines.append("")

    # Arestas
    if edges:
        lines.append("  // Arestas")
        for e in edges:
            src = _sanitize_dot_id(e.source_id)
            tgt = _sanitize_dot_id(e.target_id)
            label = e.kind
            lines.append(f'  {src} -> {tgt} [label="{label}"];')
    lines.append("}")

    return "\n".join(lines)


def export_mermaid(
    store: GraphStore,
    kind: str | None = None,
    language: str | None = None,
    limit: int | None = None,
    edge_kinds: frozenset[str] | None = None,
    diagram_type: str = "flowchart",
) -> str:
    """Exporta o grafo para formato Mermaid.

    Args:
        store: GraphStore com o grafo.
        kind: Filtrar nós por tipo.
        language: Filtrar nós por linguagem.
        limit: Máximo de nós.
        edge_kinds: Filtrar arestas por tipo.
        diagram_type: 'flowchart' (padrão) ou 'classDiagram'.

    Returns:
        String no formato Mermaid.
    """
    nodes = _fetch_nodes(store, kind=kind, language=language, limit=limit)
    node_ids = {n.id for n in nodes}
    edges = _fetch_edges_for_nodes(store, node_ids)

    if edge_kinds:
        edges = [e for e in edges if e.kind in edge_kinds]

    lines: list[str] = []

    if diagram_type == "classDiagram":
        lines.append("classDiagram")
        # Agrupa por classe para classDiagram
        classes = [n for n in nodes if n.kind == "class"]
        methods = [n for n in nodes if n.kind == "method"]
        functions = [n for n in nodes if n.kind == "function"]

        for c in classes:
            safe_id = _mermaid_safe_id(c.id)
            lines.append(f"  class {safe_id} {{")
            lines.append(f'    %% {c.name}')
            lines.append("  }")

        for m in methods:
            safe_id = _mermaid_safe_id(m.id)
            lines.append(f"  class {safe_id} {{")
            lines.append(f'    %% {m.name}()')
            lines.append("  }")

        for f in functions:
            safe_id = _mermaid_safe_id(f.id)
            lines.append(f"  class {safe_id} {{")
            lines.append(f'    %% {f.name}()')
            lines.append("  }")

        # Arestas
        kind_map = {
            "calls": "..>",
            "inherits": "--|>",
            "contains": "*--",
            "imports": "..>",
        }
        for e in edges:
            src = _mermaid_safe_id(e.source_id)
            tgt = _mermaid_safe_id(e.target_id)
            arrow = kind_map.get(e.kind, "-->")
            lines.append(f"  {src} {arrow} {tgt}")

    else:  # flowchart (padrão)
        lines.append("flowchart LR")
        # Nós
        for n in nodes:
            safe_id = _mermaid_safe_id(n.id)
            if n.kind == "class":
                shape_l, shape_r = "[[", "]]"
            elif n.kind == "function":
                shape_l, shape_r = "(", ")"
            elif n.kind == "method":
                shape_l, shape_r = ">", "]"
            else:
                shape_l, shape_r = "{", "}"
            label = n.name.replace('"', "'")
            lines.append(f'  {safe_id}{shape_l}"{label}"{shape_r}')

        # Arestas
        kind_labels = {
            "calls": "calls",
            "inherits": "inherits",
            "imports": "imports",
            "contains": "contains",
        }
        for e in edges:
            src = _mermaid_safe_id(e.source_id)
            tgt = _mermaid_safe_id(e.target_id)
            label = kind_labels.get(e.kind, e.kind)
            lines.append(f'  {src} -->|{label}| {tgt}')

    return "\n".join(lines)


def export_json(
    store: GraphStore,
    kind: str | None = None,
    language: str | None = None,
    limit: int | None = None,
    edge_kinds: frozenset[str] | None = None,
) -> str:
    """Exporta o grafo para formato JSON.

    Returns:
        String JSON com 'nodes' e 'edges'.
    """
    import json

    nodes = _fetch_nodes(store, kind=kind, language=language, limit=limit)
    node_ids = {n.id for n in nodes}
    edges = _fetch_edges_for_nodes(store, node_ids)

    if edge_kinds:
        edges = [e for e in edges if e.kind in edge_kinds]

    data = {
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "kind": n.kind,
                "file_path": n.file_path,
                "language": n.language,
                "line_start": n.line_start,
                "line_end": n.line_end,
                "docstring": n.docstring,
            }
            for n in nodes
        ],
        "edges": [
            {
                "source_id": e.source_id,
                "target_id": e.target_id,
                "kind": e.kind,
            }
            for e in edges
        ],
    }

    return json.dumps(data, indent=2, default=str)


def _mermaid_safe_id(node_id: str) -> str:
    """Sanitiza ID para Mermaid (apenas alphanumericos e underscore)."""
    return "n" + node_id.replace("-", "_")


def _compute_degrees(node_ids: set[str], edges: list[Edge]) -> dict[str, int]:
    """Calcula grau (entrada + saída) de cada nó, restrito às arestas fornecidas."""
    degrees: dict[str, int] = dict.fromkeys(node_ids, 0)
    for e in edges:
        if e.source_id in degrees:
            degrees[e.source_id] += 1
        if e.target_id in degrees:
            degrees[e.target_id] += 1
    return degrees


def export_html(
    store: GraphStore,
    kind: str | None = None,
    language: str | None = None,
    limit: int | None = None,
    edge_kinds: frozenset[str] | None = None,
) -> str:
    """Exporta o grafo para um arquivo HTML autocontido com visualização 3D.

    Usa a biblioteca 3d-force-graph (vendorizada, sem dependência de rede)
    para renderizar um grafo interativo navegável no browser: rotação/zoom,
    destaque de vizinhos ao passar o mouse, painel de detalhes ao clicar em
    um nó, e busca por nome.

    Args:
        store: GraphStore com o grafo.
        kind: Filtrar nós por tipo (function, class, method).
        language: Filtrar nós por linguagem.
        limit: Máximo de nós.
        edge_kinds: Filtrar arestas por tipo (calls, imports, inherits, contains).
            Se None, inclui todas.

    Returns:
        String HTML pronta para salvar em arquivo e abrir no browser.
    """
    nodes = _fetch_nodes(store, kind=kind, language=language, limit=limit)
    node_ids = {n.id for n in nodes}
    edges = _fetch_edges_for_nodes(store, node_ids)

    if edge_kinds:
        edges = [e for e in edges if e.kind in edge_kinds]

    degrees = _compute_degrees(node_ids, edges)

    graph_data = {
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "kind": n.kind,
                "language": n.language,
                "file_path": n.file_path,
                "line_start": n.line_start,
                "line_end": n.line_end,
                "docstring": n.docstring,
                "val": degrees.get(n.id, 0),
            }
            for n in nodes
        ],
        "links": [
            {
                "source": e.source_id,
                "target": e.target_id,
                "kind": e.kind,
            }
            for e in edges
        ],
    }

    # Escapa "</" para que docstrings/nomes contendo "</script>" não fechem a
    # tag <script type="application/json"> prematuramente quando o HTML for parseado.
    graph_json = json.dumps(graph_data, default=str).replace("</", "<\\/")

    template = resources.files("eizo.static").joinpath("graph_view.html.template").read_text(encoding="utf-8")
    vendor_js = resources.files("eizo.static.vendor").joinpath("3d-force-graph.min.js").read_text(encoding="utf-8")

    html = template.replace("__GRAPH_DATA__", graph_json).replace("__VENDOR_JS__", vendor_js)
    return html
