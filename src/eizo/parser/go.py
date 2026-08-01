"""Parser Go usando Tree-sitter.

Extrai funções, structs/interfaces (como 'class'), métodos, imports e
chamadas de arquivos .go.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

from eizo.graph.models import Edge, Node
from eizo.parser.base import BaseParser

# Carrega a linguagem Go do pacote tree-sitter-go
try:
    from tree_sitter_go import language as go_language

    _capsule = go_language()
    GO_LANGUAGE: Language | None = Language(_capsule)
except ImportError:
    GO_LANGUAGE = None


def _node_id(name: str, file_path: str, line: int, column: int = 0) -> str:
    """Gera um ID único para um nó.

    Inclui a coluna além da linha: arquivos gerados/minificados podem colocar
    múltiplos símbolos na mesma linha — "arquivo:nome:linha" sozinho colidiria
    entre eles (ver mesma correção aplicada aos parsers Python e TypeScript).
    """
    raw = f"{file_path}:{name}:{line}:{column}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_text(source: bytes, node: Any) -> str:
    """Extrai texto de um nó Tree-sitter."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _unwrap_pointer(node: Any) -> Any:
    """Desembrulha `*Tipo` (pointer_type) para o `type_identifier` de dentro.

    Usado tanto no receiver de um método (`func (d *Dog) ...`) quanto em
    campos embutidos de struct — em ambos os casos o nome do tipo é o que
    importa, não se é passado por ponteiro ou valor.
    """
    if node.type == "pointer_type":
        for child in node.children:
            if child.type == "type_identifier":
                return child
        return None
    if node.type == "type_identifier":
        return node
    return None


def _prescan_type_positions(root: Any, source: bytes) -> dict[str, tuple[int, int]]:
    """Localiza a posição (linha, coluna) de cada struct/interface do arquivo.

    Métodos Go (`func (r Receiver) Nome() {}`) não são sintaticamente
    aninhados dentro do tipo do receiver — ao contrário de Python/TS, onde um
    método está dentro do corpo da classe. Para ligar um método ao seu tipo
    via aresta 'contains' é preciso conhecer a posição do tipo de antemão,
    independente da ordem de declaração no arquivo (o receiver pode aparecer
    antes ou depois do `type Dog struct {...}`).
    """
    positions: dict[str, tuple[int, int]] = {}

    def walk(node: Any) -> None:
        if node.type == "type_spec":
            name_node = node.child_by_field_name("name")
            type_node = node.child_by_field_name("type")
            if name_node is not None and type_node is not None and type_node.type in ("struct_type", "interface_type"):
                name = _get_text(source, name_node)
                positions[name] = (name_node.start_point[0] + 1, name_node.start_point[1])
        for child in node.children:
            walk(child)

    walk(root)
    return positions


class GoParser(BaseParser):
    """Parser para Go."""

    @property
    def language(self) -> str:
        return "go"

    @property
    def extensions(self) -> set[str]:
        return {".go"}

    def __init__(self) -> None:
        if GO_LANGUAGE is None:
            msg = "tree-sitter-go não está instalado. Execute: pip install tree-sitter-go"
            raise RuntimeError(msg)
        self._parser = Parser(GO_LANGUAGE)

    def parse_file(self, file_path: Path, source: str) -> tuple[list[Node], list[Edge]]:
        """Parseia um arquivo Go."""
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
            language="go",
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
    ) -> None:
        """Percorre a AST recursivamente extraindo símbolos."""
        node_type = node.type

        if node_type == "function_declaration":
            self._handle_function(node, source, file_path, nodes, edges, parent_id, type_positions)
        elif node_type == "method_declaration":
            self._handle_method(node, source, file_path, nodes, edges, type_positions)
        elif node_type == "type_spec":
            self._handle_type_spec(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "import_spec":
            self._handle_import(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "call_expression":
            self._handle_call(node, source, file_path, nodes, edges, parent_id)
            # Continua recursão dentro da call (ex: argumentos) para capturar
            # chamadas aninhadas como `outer(inner())` — mesmo parent_id, pois
            # o call em si não introduz um novo escopo de função.
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id, type_positions)
        else:
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id, type_positions)

    def _handle_function(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
        type_positions: dict[str, tuple[int, int]],
    ) -> None:
        """Extrai uma função top-level (`func Nome(...) {...}`)."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        start_col = node.start_point[1]
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)

        func_node = Node(
            id=_node_id(name, file_path, start_line, start_col),
            name=name,
            kind="function",
            file_path=file_path,
            language="go",
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

    def _handle_method(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        type_positions: dict[str, tuple[int, int]],
    ) -> None:
        """Extrai um método (`func (r Receiver) Nome(...) {...}`).

        O receiver não é filho sintático do tipo — resolve o `parent_id` pela
        posição pré-escaneada do tipo (ver `_prescan_type_positions`).
        """
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        start_col = node.start_point[1]
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)

        method_node = Node(
            id=_node_id(name, file_path, start_line, start_col),
            name=name,
            kind="method",
            file_path=file_path,
            language="go",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(method_node)

        parent_id = self._resolve_receiver_parent(node, source, file_path, type_positions)
        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=method_node.id, kind="contains"))

        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self._walk_tree(child, source, file_path, nodes, edges, method_node.id, type_positions)

    def _resolve_receiver_parent(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        type_positions: dict[str, tuple[int, int]],
    ) -> str | None:
        """Resolve o id do struct/interface dono do receiver, se conhecido no arquivo."""
        receiver = node.child_by_field_name("receiver")
        if receiver is None:
            return None
        for child in receiver.children:
            if child.type != "parameter_declaration":
                continue
            type_field = child.child_by_field_name("type")
            if type_field is None:
                continue
            type_id_node = _unwrap_pointer(type_field)
            if type_id_node is None:
                continue
            type_name = _get_text(source, type_id_node)
            position = type_positions.get(type_name)
            if position is None:
                return None
            return _node_id(type_name, file_path, position[0], position[1])
        return None

    def _handle_type_spec(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai `type Nome struct {...}` / `type Nome interface {...}` como 'class'.

        Outros type aliases (`type ID = string`) são ignorados — não
        representam um símbolo estruturado equivalente a classe.
        """
        name_node = node.child_by_field_name("name")
        type_node = node.child_by_field_name("type")
        if name_node is None or type_node is None or type_node.type not in ("struct_type", "interface_type"):
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
            language="go",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(class_node)

        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=class_node.id, kind="contains"))

        if type_node.type == "struct_type":
            self._handle_embedded_fields(type_node, source, file_path, class_node.id, nodes, edges)

    def _handle_embedded_fields(
        self,
        struct_node: Any,
        source: bytes,
        file_path: str,
        class_id: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        """Campos embutidos (`struct { Animal }`, sem nome próprio) viram 'inherits'.

        É o análogo mais próximo de herança que Go possui: o struct ganha os
        métodos/campos do tipo embutido por composição.
        """
        field_list = next(
            (c for c in struct_node.children if c.type == "field_declaration_list"), None
        )
        if field_list is None:
            return
        for field_decl in field_list.children:
            if field_decl.type != "field_declaration":
                continue
            if field_decl.child_by_field_name("name") is not None:
                continue  # campo nomeado normal, não é embedding
            type_field = field_decl.child_by_field_name("type")
            if type_field is None:
                continue
            type_id_node = _unwrap_pointer(type_field)
            if type_id_node is None:
                continue

            base_name = _get_text(source, type_id_node)
            base_line = type_id_node.start_point[0] + 1
            base_col = type_id_node.start_point[1]
            base_id = _node_id(base_name, file_path, base_line, base_col)
            base_node = Node(
                id=base_id,
                name=base_name,
                kind="class",
                file_path=file_path,
                language="go",
                line_start=base_line,
                line_end=base_line,
                metadata={"external": True},
            )
            nodes.append(base_node)
            edges.append(Edge(
                source_id=class_id,
                target_id=base_id,
                kind="inherits",
                metadata={"base_name": base_name},
            ))

    def _handle_import(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai `import_spec` (path entre aspas, com ou sem alias/blank)."""
        path_node = node.child_by_field_name("path")
        if path_node is None:
            return

        import_path = _get_text(source, path_node).strip('"')
        import_node = Node(
            id=_node_id(f"import:{import_path}", file_path, path_node.start_point[0] + 1, path_node.start_point[1]),
            name=import_path,
            kind="import",
            file_path=file_path,
            language="go",
            line_start=path_node.start_point[0] + 1,
            line_end=path_node.end_point[0] + 1,
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
        """Extrai chamadas de função (`f()`) e método (`obj.Metodo()`)."""
        func_node = node.child_by_field_name("function")
        if func_node is None:
            return

        # Posição correta para chamadas encadeadas ("x.f().f()"): usa o
        # identificador do campo/método (`field`), não `func_node` inteiro
        # (o "selector_expression" completo, que começa no operando `x`) —
        # senão as duas chamadas a `f` colidiriam no mesmo id (mesma
        # correção aplicada aos parsers Python e TypeScript).
        if func_node.type == "identifier":
            call_name = _get_text(source, func_node)
            name_node = func_node
        elif func_node.type == "selector_expression":
            field = func_node.child_by_field_name("field")
            if field is None:
                return
            call_name = _get_text(source, field)
            name_node = field
        else:
            return

        call_line = name_node.start_point[0] + 1
        call_col = name_node.start_point[1]
        call_node = Node(
            id=_node_id(f"call:{call_name}", file_path, call_line, call_col),
            name=call_name,
            kind="call",
            file_path=file_path,
            language="go",
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
