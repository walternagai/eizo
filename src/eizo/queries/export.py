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
from pathlib import Path
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


def _is_architecture_file(file_path: str) -> bool:
    """Filtra arquivos que fazem parte da arquitetura de runtime.

    Exclui testes, assets binários/vendor, __init__.py meramente estruturais
    e arquivos de cache.
    """
    lower = file_path.replace("\\", "/").lower()
    if "/tests/" in lower or lower.startswith("tests/"):
        return False
    if "/static/vendor/" in lower:
        return False
    if lower.endswith("/__init__.py"):
        return False
    return "/__pycache__/" not in lower


def _relative_repo_path(file_path: str, repo_root: str | None = None) -> str:
    """Torna o caminho do arquivo relativo ao repo_root quando possível."""
    if repo_root:
        try:
            return str(Path(file_path).resolve().relative_to(Path(repo_root).resolve()))
        except (ValueError, OSError):
            pass
    return file_path


def _layer_for_file(file_path: str) -> str:
    """Mapeia um caminho relativo de arquivo para uma camada arquitetural.

    Usa segmentos do path para classificar componentes em camadas de alto
    nível. Caminho vazio ou não reconhecido vai para 'other'.
    """
    lower = file_path.replace("\\", "/").lower()
    if "/cli.py" in lower or "/__main__.py" in lower or "/mcp/server.py" in lower:
        return "entrypoints"
    if "/queries/" in lower:
        return "queries"
    if "/parser/" in lower:
        return "parsers"
    if "/graph/" in lower:
        return "graph"
    if "/indexer.py" in lower:
        return "indexer"
    if "/static/" in lower:
        return "static"
    return "other"


def _file_stem(file_path: str) -> str:
    """Retorna o nome do arquivo sem extensão, normalizado para Mermaid."""
    return Path(file_path).stem


def _common_path_prefix(paths: list[str]) -> str:
    """Retorna o maior prefixo comum entre os caminhos (em segmentos)."""
    if not paths:
        return ""
    split_paths = [p.replace("\\", "/").split("/") for p in paths]
    prefix_parts: list[str] = []
    for parts in zip(*split_paths, strict=False):
        if all(part == parts[0] for part in parts):
            prefix_parts.append(parts[0])
        else:
            break
    return "/".join(prefix_parts)


def _component_id(file_path: str, prefix: str) -> str:
    """Gera um ID Mermaid seguro a partir do caminho relativo do arquivo."""
    rel = _relative_repo_path(file_path, prefix)
    cleaned = rel.replace("\\", "/").replace("src/", "").replace("/", "_")
    cleaned = cleaned.replace(".", "_").replace("-", "_")
    return "comp_" + cleaned


def _display_path(file_path: str, prefix: str) -> str:
    """Retorna caminho legível para exibição no diagrama."""
    rel = _relative_repo_path(file_path, prefix)
    # Remove prefixo src/ se presente
    if rel.startswith("src/"):
        rel = rel[4:]
    return rel


def _sanitize_label(text: str) -> str:
    """Escapa caracteres problemáticos em labels Mermaid."""
    return text.replace('"', "'")


def export_architecture_mermaid(store: GraphStore) -> str:
    """Exporta uma visão arquitetural rica do repositório para Mermaid.

    O diagrama mostra:

    - Camadas macro (CLI/MCP, queries, graph, parsers, indexer, static)
      como subgraphs.
    - Os componentes funcionais principais dentro de cada camada (arquivos
      com maior grau de conectividade e nós de definição relevantes).
    - Dependências entre componentes reais derivadas do grafo, resolvendo
      call sites e import stubs para as definições reais.
    - Resumo estatístico e linguagens do repositório.

    A visualização prioriza componentes que participam de relações
    significativas (chamadas, imports, herança), deixando de fora nós
    isolados, arquivos de teste e vendors externos.

    Returns:
        String no formato Mermaid (graph TD).
    """
    stats = store.get_stats()
    nodes = _fetch_nodes(store)
    if not nodes:
        return "graph TD\n  empty[Grafo vazio — execute eizo init]"

    # Mapeia cada nó para sua camada e arquivo
    node_layer: dict[str, str] = {}
    node_file: dict[str, Node] = {}
    file_nodes: dict[str, set[str]] = {}
    for n in nodes:
        if not _is_architecture_file(n.file_path):
            continue
        node_layer[n.id] = _layer_for_file(n.file_path)
        node_file[n.id] = n
        file_nodes.setdefault(n.file_path, set()).add(n.id)

    if not file_nodes:
        return "graph TD\n  empty[Nenhum componente de arquitetura encontrado]"

    # Calcula prefixo comum para mostrar caminhos relativos no diagrama
    common_prefix = _common_path_prefix(list(file_nodes.keys()))

    # Resolve dependências reais entre arquivos.
    # Para cada nó de definição, usamos get_real_references para achar quem o
    # referencia (calls/imports/inherits). Para outgoing, resolvemos call sites
    # para definições reais. Isso captura as relações que o parser representa
    # via nós intermediários.
    file_deps: dict[tuple[str, str], set[str]] = {}
    definition_nodes = [n for n in nodes if n.kind in ("function", "method", "class")]

    for node in definition_nodes:
        if node.file_path not in file_nodes:
            continue
        for referrer, kind in store.get_real_references(node.id, node.name):
            ref_file = referrer.file_path
            if ref_file == node.file_path or ref_file not in file_nodes:
                continue
            key = (ref_file, node.file_path)
            file_deps.setdefault(key, set()).add(kind)

    for node in nodes:
        if node.file_path not in file_nodes:
            continue
        if node.kind != "call":
            continue
        resolved = store.resolve_call_to_definition(node)
        if resolved.id == node.id or resolved.file_path == node.file_path:
            continue
        if resolved.file_path not in file_nodes:
            continue
        key = (node.file_path, resolved.file_path)
        file_deps.setdefault(key, set()).add("calls")

    # Calcula grau de cada arquivo a partir das dependências reais
    file_degrees: dict[str, int] = dict.fromkeys(file_nodes, 0)
    for (src, tgt), kinds in file_deps.items():
        weight = len(kinds)
        file_degrees[src] += weight
        file_degrees[tgt] += weight

    # Agrupa arquivos por camada
    layer_files: dict[str, set[str]] = {}
    for file_path in file_nodes:
        layer = _layer_for_file(file_path)
        layer_files.setdefault(layer, set()).add(file_path)

    # Seleciona componentes principais por camada
    layer_components: dict[str, list[str]] = {}
    selected_files: set[str] = set()
    for layer, files in layer_files.items():
        if not files:
            continue
        ranked = sorted(
            files,
            key=lambda f: (file_degrees.get(f, 0), len(file_nodes.get(f, set()))),
            reverse=True,
        )
        # Limita número de componentes por camada para manter legibilidade
        limit = 6 if layer in ("entrypoints", "queries", "graph", "parsers", "indexer") else 3
        chosen = ranked[:limit]
        layer_components[layer] = chosen
        selected_files.update(chosen)

    # Garante que toda camada identificada tenha pelo menos um representante
    for layer, files in layer_files.items():
        if layer not in layer_components and files:
            layer_components[layer] = [next(iter(sorted(files)))]
            selected_files.add(layer_components[layer][0])

    # Arestas entre componentes selecionados
    component_edges: dict[tuple[str, str], set[str]] = {}
    for (src, tgt), kinds in file_deps.items():
        if src not in selected_files or tgt not in selected_files:
            continue
        component_edges[(src, tgt)] = kinds

    # Rótulos amigáveis para camadas
    layer_labels: dict[str, str] = {
        "entrypoints": "Entrypoints (CLI / MCP)",
        "queries": "Query Layer",
        "graph": "Graph Layer",
        "parsers": "Language Parsers",
        "indexer": "Indexer",
        "static": "Static Assets",
        "other": "Other",
    }

    lines: list[str] = ["graph TD"]
    lines.append('  classDef layerClass fill:#f9f,stroke:#333,stroke-width:2px;')
    lines.append('  classDef componentClass fill:#e1f5e1,stroke:#333,stroke-width:1px;')
    lines.append('  classDef statsClass fill:#fff4cc,stroke:#333,stroke-width:1px;')

    # Subgraphs por camada
    for layer in ("entrypoints", "queries", "graph", "parsers", "indexer", "static", "other"):
        components = layer_components.get(layer)
        if not components:
            continue
        label = layer_labels.get(layer, layer)
        lines.append(f'  subgraph {layer}["{_sanitize_label(label)}"]')
        for file_path in components:
            safe_id = _component_id(file_path, common_prefix)
            stem = _file_stem(file_path)
            count = len(file_nodes.get(file_path, set()))
            deg = file_degrees.get(file_path, 0)
            desc = _component_description(file_path)
            label_text = f"{stem}<br/>{desc}<br/>~{count} symbols, {deg} links"
            lines.append(f'    {safe_id}["{_sanitize_label(label_text)}"]')
            lines.append(f"    class {safe_id} componentClass;")
        lines.append("  end")
        if components:
            first_id = _component_id(components[0], common_prefix)
            lines.append(f"  class {first_id} layerClass;")

    # Arestas entre componentes
    for (src, tgt), kinds in sorted(component_edges.items()):
        src_id = _component_id(src, common_prefix)
        tgt_id = _component_id(tgt, common_prefix)
        label = ", ".join(sorted(kinds))
        lines.append(f'  {src_id} -->|"{_sanitize_label(label)}"| {tgt_id}')

    # Resumo estatístico
    lines.append("")
    lines.append('  subgraph Stats["Repository Stats"]')
    lines.append(f'    total_nodes["Total nodes: {stats.total_nodes}"]')
    lines.append(f'    total_edges["Total edges: {stats.total_edges}"]')
    lines.append(f'    total_files["Total files: {stats.total_files}"]')
    lines.append(f'    languages["Languages: {", ".join(stats.by_language.keys()) or "-"}"]')
    lines.append("  end")
    lines.append("  class total_nodes,total_edges,total_files,languages statsClass;")

    return "\n".join(lines)


def _component_description(file_path: str) -> str:
    """Retorna uma descrição curta do papel de um arquivo no sistema."""
    lower = file_path.replace("\\", "/").lower()
    descriptions: dict[str, str] = {
        "/cli.py": "CLI Click",
        "/__main__.py": "entry point",
        "/mcp/server.py": "MCP server",
        "/indexer.py": "orchestrates indexing",
        "/graph/store.py": "SQLite CRUD",
        "/graph/schema.py": "DB schema",
        "/graph/models.py": "Node/Edge models",
        "/queries/search.py": "symbol search",
        "/queries/trace.py": "call graph trace",
        "/queries/impact.py": "impact analysis",
        "/queries/analysis.py": "dead code & hotspots",
        "/queries/export.py": "DOT/Mermaid/JSON/HTML export",
        "/parser/python.py": "Python parser",
        "/parser/typescript.py": "TypeScript parser",
        "/parser/base.py": "parser base",
    }
    for key, desc in descriptions.items():
        if key in lower:
            return desc
    return "component"


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
