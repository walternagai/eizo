"""Parser Rust usando Tree-sitter.

Extrai funções, structs/traits/enums (como 'class'), métodos (via `impl`),
imports (`use`) e chamadas de arquivos .rs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

from eizo.graph.models import Edge, Node
from eizo.parser.base import BaseParser

# Carrega a linguagem Rust do pacote tree-sitter-rust
try:
    from tree_sitter_rust import language as rust_language

    _capsule = rust_language()
    RUST_LANGUAGE: Language | None = Language(_capsule)
except ImportError:
    RUST_LANGUAGE = None

# type_spec-equivalentes: nós Rust que viram 'class' no grafo.
_TYPE_ITEM_KINDS: frozenset[str] = frozenset({"struct_item", "trait_item", "enum_item"})


def _node_id(name: str, file_path: str, line: int, column: int = 0) -> str:
    """Gera um ID único para um nó.

    Inclui a coluna além da linha: arquivos gerados/minificados podem colocar
    múltiplos símbolos na mesma linha — "arquivo:nome:linha" sozinho colidiria
    entre eles (ver mesma correção aplicada aos parsers Python, TypeScript e Go).
    """
    raw = f"{file_path}:{name}:{line}:{column}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_text(source: bytes, node: Any) -> str:
    """Extrai texto de um nó Tree-sitter."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _prescan_type_positions(root: Any, source: bytes) -> dict[str, tuple[int, int]]:
    """Localiza a posição (linha, coluna) de cada struct/trait/enum do arquivo.

    Blocos `impl Tipo { ... }` referenciam o tipo pelo nome, não por
    aninhamento sintático — ao contrário de Python/TS, onde um método está
    dentro do corpo da classe. Para ligar métodos de um `impl` ao seu tipo via
    aresta 'contains' é preciso conhecer a posição do tipo de antemão,
    independente de o `impl` aparecer antes ou depois de `struct Tipo {...}`
    no arquivo, e do tipo poder ter múltiplos blocos `impl` (um por trait).
    """
    positions: dict[str, tuple[int, int]] = {}

    def walk(node: Any) -> None:
        if node.type in _TYPE_ITEM_KINDS:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _get_text(source, name_node)
                positions[name] = (name_node.start_point[0] + 1, name_node.start_point[1])
        for child in node.children:
            walk(child)

    walk(root)
    return positions


def _resolve_use_paths(node: Any, prefix: str, source: bytes) -> list[tuple[str, Any]]:
    """Resolve um `use` (possivelmente aninhado/agrupado) em pares (nome_completo, nó_posição).

    `use` em Rust é bem mais expressivo que `import` em Python/Go: suporta
    grupos (`use std::{io, fs::File}`), alias (`use X as Y`) e glob
    (`use std::io::*`) — todos resolvidos recursivamente aqui, prefixando o
    caminho acumulado dos grupos aninhados.
    """
    if node.type == "identifier":
        text = _get_text(source, node)
        return [(f"{prefix}{text}", node)]
    if node.type == "scoped_identifier":
        text = _get_text(source, node)
        return [(f"{prefix}{text}", node)]
    if node.type == "use_as_clause":
        # Resolve pelo nome real (path), não pelo alias local — mesma
        # convenção usada em 'from x import y as z' no parser Python.
        path = node.child_by_field_name("path")
        if path is None:
            return []
        return _resolve_use_paths(path, prefix, source)
    if node.type == "use_wildcard":
        inner = next((c for c in node.children if c.type not in ("::", "*")), None)
        if inner is None:
            return []
        base = _get_text(source, inner)
        return [(f"{prefix}{base}::*", inner)]
    if node.type == "scoped_use_list":
        path = node.child_by_field_name("path")
        list_node = node.child_by_field_name("list")
        if path is None or list_node is None:
            return []
        new_prefix = f"{prefix}{_get_text(source, path)}::"
        results: list[tuple[str, Any]] = []
        for item in list_node.children:
            if item.type in ("{", "}", ","):
                continue
            results.extend(_resolve_use_paths(item, new_prefix, source))
        return results
    if node.type == "use_list":
        results = []
        for item in node.children:
            if item.type in ("{", "}", ","):
                continue
            results.extend(_resolve_use_paths(item, prefix, source))
        return results
    return []


class RustParser(BaseParser):
    """Parser para Rust."""

    @property
    def language(self) -> str:
        return "rust"

    @property
    def extensions(self) -> set[str]:
        return {".rs"}

    def __init__(self) -> None:
        if RUST_LANGUAGE is None:
            msg = "tree-sitter-rust não está instalado. Execute: pip install tree-sitter-rust"
            raise RuntimeError(msg)
        self._parser = Parser(RUST_LANGUAGE)

    def parse_file(self, file_path: Path, source: str) -> tuple[list[Node], list[Edge]]:
        """Parseia um arquivo Rust."""
        source_bytes = source.encode("utf-8")
        tree = self._parser.parse(source_bytes)
        nodes: list[Node] = []
        edges: list[Edge] = []
        file_path_str = str(file_path)

        file_node = Node(
            id=_node_id("__file__", file_path_str, 0),
            name=file_path.name,
            kind="file",
            file_path=file_path_str,
            language="rust",
            line_start=1,
            line_end=source.count("\n") + 1,
        )
        nodes.append(file_node)

        type_positions = _prescan_type_positions(tree.root_node, source_bytes)

        self._walk_tree(
            tree.root_node,
            source_bytes,
            file_path_str,
            nodes,
            edges,
            file_node.id,
            type_positions,
        )

        return nodes, edges

    def _walk_tree(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
        type_positions: dict[str, tuple[int, int]],
        in_type_scope: bool = False,
    ) -> None:
        """Percorre a AST recursivamente extraindo símbolos.

        `in_type_scope` indica se estamos dentro de um `impl`/`trait` (então
        `function_item` deve virar 'method'), independente de `parent_id` ter
        sido resolvido — um `impl` para um tipo desconhecido no arquivo ainda
        contém métodos, só não gera a aresta 'contains'.
        """
        node_type = node.type

        if node_type == "function_item":
            self._handle_function(node, source, file_path, nodes, edges, parent_id, type_positions, in_type_scope)
        elif node_type in _TYPE_ITEM_KINDS:
            self._handle_type_item(node, source, file_path, nodes, edges, parent_id, type_positions)
        elif node_type == "impl_item":
            self._handle_impl(node, source, file_path, nodes, edges, type_positions)
        elif node_type == "use_declaration":
            self._handle_use(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "call_expression":
            self._handle_call(node, source, file_path, nodes, edges, parent_id)
            # Continua recursão dentro da call (ex: argumentos) para capturar
            # chamadas aninhadas como `outer(inner())` — mesmo parent_id, pois
            # o call em si não introduz um novo escopo de função.
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id, type_positions, in_type_scope)
        else:
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id, type_positions, in_type_scope)

    def _handle_function(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
        type_positions: dict[str, tuple[int, int]],
        in_type_scope: bool,
    ) -> None:
        """Extrai uma função (`fn nome(...) {...}`) — top-level, dentro de um
        `mod`, ou método dentro de um `impl`/`trait` (`in_type_scope=True`)."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        start_col = node.start_point[1]
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)

        kind = "method" if in_type_scope else "function"

        func_node = Node(
            id=_node_id(name, file_path, start_line, start_col),
            name=name,
            kind=kind,
            file_path=file_path,
            language="rust",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(func_node)

        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=func_node.id, kind="contains"))

        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self._walk_tree(child, source, file_path, nodes, edges, func_node.id, type_positions)

    def _handle_type_item(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
        type_positions: dict[str, tuple[int, int]],
    ) -> None:
        """Extrai `struct`/`trait`/`enum` como 'class' — Rust não tem classes."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = name_node.start_point[0] + 1
        start_col = name_node.start_point[1]
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)

        class_node = Node(
            id=_node_id(name, file_path, start_line, start_col),
            name=name,
            kind="class",
            file_path=file_path,
            language="rust",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(class_node)

        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=class_node.id, kind="contains"))

        # `trait_item` pode ter métodos com corpo default — ainda são
        # métodos do próprio trait (não de um `impl` externo).
        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self._walk_tree(
                    child, source, file_path, nodes, edges, class_node.id, type_positions, in_type_scope=True
                )

    def _handle_impl(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        type_positions: dict[str, tuple[int, int]],
    ) -> None:
        """Extrai um bloco `impl Tipo {...}` / `impl Trait for Tipo {...}`.

        As funções dentro do impl viram métodos do `Tipo`, resolvido pela
        posição pré-escaneada (ver `_prescan_type_positions`) — o mesmo
        problema de ordem de declaração que existe nos métodos Go, só que
        aqui a estrutura sintática (impl -> declaration_list -> function_item)
        já resolve o aninhamento; só falta encontrar o id do tipo alvo.
        """
        type_field = node.child_by_field_name("type")
        body = node.child_by_field_name("body")
        if type_field is None or body is None:
            return

        type_name = _get_text(source, type_field)
        position = type_positions.get(type_name)
        parent_id = _node_id(type_name, file_path, position[0], position[1]) if position else None

        trait_field = node.child_by_field_name("trait")
        if trait_field is not None and parent_id is not None:
            trait_name = _get_text(source, trait_field)
            trait_position = type_positions.get(trait_name)
            if trait_position is not None:
                trait_id = _node_id(trait_name, file_path, trait_position[0], trait_position[1])
                edges.append(Edge(
                    source_id=parent_id,
                    target_id=trait_id,
                    kind="inherits",
                    metadata={"base_name": trait_name},
                ))
            else:
                trait_id = _node_id(trait_name, file_path, node.start_point[0] + 1, node.start_point[1])
                nodes.append(Node(
                    id=trait_id,
                    name=trait_name,
                    kind="class",
                    file_path=file_path,
                    language="rust",
                    line_start=node.start_point[0] + 1,
                    line_end=node.start_point[0] + 1,
                    metadata={"external": True},
                ))
                edges.append(Edge(
                    source_id=parent_id,
                    target_id=trait_id,
                    kind="inherits",
                    metadata={"base_name": trait_name},
                ))

        for child in body.children:
            self._walk_tree(
                child, source, file_path, nodes, edges, parent_id, type_positions, in_type_scope=True
            )

    def _handle_use(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai imports (`use ...;`), incluindo grupos, alias e glob."""
        argument = node.child_by_field_name("argument")
        if argument is None:
            return

        for import_name, position_node in _resolve_use_paths(argument, "", source):
            import_node = Node(
                id=_node_id(
                    f"import:{import_name}",
                    file_path,
                    position_node.start_point[0] + 1,
                    position_node.start_point[1],
                ),
                name=import_name,
                kind="import",
                file_path=file_path,
                language="rust",
                line_start=position_node.start_point[0] + 1,
                line_end=position_node.end_point[0] + 1,
            )
            nodes.append(import_node)
            if parent_id:
                edges.append(Edge(source_id=parent_id, target_id=import_node.id, kind="imports"))

    def _handle_call(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai chamadas: `f()`, `obj.metodo()` e `Tipo::associada()`."""
        func_node = node.child_by_field_name("function")
        if func_node is None:
            return

        # Posição correta para chamadas encadeadas ("x.f().f()"): usa o
        # identificador do campo/nome chamado, não o nó `function` inteiro
        # (que para "field_expression"/"scoped_identifier" começa no
        # operando/caminho, não no nome) — senão duas chamadas encadeadas ao
        # mesmo nome colidiriam no mesmo id (mesma correção aplicada aos
        # parsers Python, TypeScript e Go).
        if func_node.type == "identifier":
            call_name = _get_text(source, func_node)
            name_node = func_node
        elif func_node.type == "field_expression":
            field = func_node.child_by_field_name("field")
            if field is None:
                return
            call_name = _get_text(source, field)
            name_node = field
        elif func_node.type == "scoped_identifier":
            name = func_node.child_by_field_name("name")
            if name is None:
                return
            call_name = _get_text(source, name)
            name_node = name
        else:
            return

        call_line = name_node.start_point[0] + 1
        call_col = name_node.start_point[1]
        call_node = Node(
            id=_node_id(f"call:{call_name}", file_path, call_line, call_col),
            name=call_name,
            kind="call",
            file_path=file_path,
            language="rust",
            line_start=call_line,
        )
        nodes.append(call_node)

        if parent_id:
            edges.append(Edge(
                source_id=parent_id,
                target_id=call_node.id,
                kind="calls",
                metadata={"call_name": call_name},
            ))
