"""Parser Java usando Tree-sitter.

Extrai classes/interfaces/enums/records (como 'class'), métodos/construtores,
imports e chamadas de arquivos .java.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

from eizo.graph.models import Edge, Node
from eizo.parser.base import BaseParser

# Carrega a linguagem Java do pacote tree-sitter-java
try:
    from tree_sitter_java import language as java_language

    _capsule = java_language()
    JAVA_LANGUAGE: Language | None = Language(_capsule)
except ImportError:
    JAVA_LANGUAGE = None

# Nós Java que viram 'class' no grafo — Java não distingue como Go/Rust,
# então todos são tratados igual (métodos ficam sintaticamente aninhados no
# corpo em todos os casos, ao contrário do impl/receiver de Go e Rust).
_TYPE_DECL_KINDS: frozenset[str] = frozenset({
    "class_declaration", "interface_declaration", "enum_declaration", "record_declaration",
})
_METHOD_DECL_KINDS: frozenset[str] = frozenset({"method_declaration", "constructor_declaration"})


def _node_id(name: str, file_path: str, line: int, column: int = 0) -> str:
    """Gera um ID único para um nó.

    Inclui a coluna além da linha: arquivos gerados/minificados podem colocar
    múltiplos símbolos na mesma linha — "arquivo:nome:linha" sozinho colidiria
    entre eles (ver mesma correção aplicada aos demais parsers).
    """
    raw = f"{file_path}:{name}:{line}:{column}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_text(source: bytes, node: Any) -> str:
    """Extrai texto de um nó Tree-sitter."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


class JavaParser(BaseParser):
    """Parser para Java."""

    @property
    def language(self) -> str:
        return "java"

    @property
    def extensions(self) -> set[str]:
        return {".java"}

    def __init__(self) -> None:
        if JAVA_LANGUAGE is None:
            msg = "tree-sitter-java não está instalado. Execute: pip install tree-sitter-java"
            raise RuntimeError(msg)
        self._parser = Parser(JAVA_LANGUAGE)

    def parse_file(self, file_path: Path, source: str) -> tuple[list[Node], list[Edge]]:
        """Parseia um arquivo Java."""
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
            language="java",
            line_start=1,
            line_end=source.count("\n") + 1,
        )
        nodes.append(file_node)

        self._walk_tree(tree.root_node, source_bytes, file_path_str, nodes, edges, file_node.id)

        return nodes, edges

    def _walk_tree(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Percorre a AST recursivamente extraindo símbolos."""
        node_type = node.type

        if node_type in _TYPE_DECL_KINDS:
            self._handle_type_decl(node, source, file_path, nodes, edges, parent_id)
        elif node_type in _METHOD_DECL_KINDS:
            self._handle_method(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "import_declaration":
            self._handle_import(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "method_invocation":
            self._handle_call(node, source, file_path, nodes, edges, parent_id)
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id)
        elif node_type == "object_creation_expression":
            self._handle_object_creation(node, source, file_path, nodes, edges, parent_id)
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id)
        else:
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id)

    def _handle_type_decl(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai `class`/`interface`/`enum`/`record` como 'class'."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        start_col = node.start_point[1]
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)

        class_node = Node(
            id=_node_id(name, file_path, start_line, start_col),
            name=name,
            kind="class",
            file_path=file_path,
            language="java",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(class_node)

        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=class_node.id, kind="contains"))

        self._handle_inheritance(node, source, file_path, class_node.id, nodes, edges)

        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self._walk_tree(child, source, file_path, nodes, edges, class_node.id)

    def _handle_inheritance(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        class_id: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        """Extrai `extends`/`implements` (classe) e `extends` (interface) como 'inherits'.

        Cobre os três formatos: `class X extends Y` (campo 'superclass'),
        `class X implements A, B` (campo 'interfaces', pode ter mais de um
        tipo), e `interface X extends A, B` (sem campo nomeado — é o único
        caso sem field name na gramática).
        """
        base_type_nodes: list[Any] = []

        superclass = node.child_by_field_name("superclass")
        if superclass is not None:
            base_type_nodes.extend(c for c in superclass.children if c.type == "type_identifier")

        interfaces = node.child_by_field_name("interfaces")
        if interfaces is not None:
            type_list = next((c for c in interfaces.children if c.type == "type_list"), None)
            if type_list is not None:
                base_type_nodes.extend(c for c in type_list.children if c.type == "type_identifier")

        extends_interfaces = next((c for c in node.children if c.type == "extends_interfaces"), None)
        if extends_interfaces is not None:
            type_list = next((c for c in extends_interfaces.children if c.type == "type_list"), None)
            if type_list is not None:
                base_type_nodes.extend(c for c in type_list.children if c.type == "type_identifier")

        for base in base_type_nodes:
            base_name = _get_text(source, base)
            base_line = base.start_point[0] + 1
            base_col = base.start_point[1]
            base_id = _node_id(base_name, file_path, base_line, base_col)
            base_node = Node(
                id=base_id,
                name=base_name,
                kind="class",
                file_path=file_path,
                language="java",
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

    def _handle_method(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai método (`method_declaration`) ou construtor (`constructor_declaration`).

        Sempre 'method': em Java todo método/construtor vive dentro de um
        `class`/`interface`/`enum`/`record` — não existe função top-level
        como em Python/Go/Rust.
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
            language="java",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(method_node)

        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=method_node.id, kind="contains"))

        # Métodos abstratos de interface (`String speak();`) não têm body.
        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self._walk_tree(child, source, file_path, nodes, edges, method_node.id)

    def _handle_import(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai `import` (com ou sem `static`, com ou sem `.*` wildcard)."""
        path_node = next((c for c in node.children if c.type in ("scoped_identifier", "identifier")), None)
        if path_node is None:
            return

        import_path = _get_text(source, path_node)
        is_wildcard = any(c.type == "asterisk" for c in node.children)
        if is_wildcard:
            import_path = f"{import_path}.*"

        import_node = Node(
            id=_node_id(f"import:{import_path}", file_path, path_node.start_point[0] + 1, path_node.start_point[1]),
            name=import_path,
            kind="import",
            file_path=file_path,
            language="java",
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
        """Extrai chamadas de método: `f()` e `obj.metodo()`.

        O campo 'name' do `method_invocation` já é o identificador do método
        chamado (não o receiver) em ambos os casos — ao contrário de
        Python/TS/Go/Rust, a gramática Java não exige desembrulhar um nó
        "attribute"/"selector"/"field_expression" para chegar nele.
        """
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        call_name = _get_text(source, name_node)
        call_line = name_node.start_point[0] + 1
        call_col = name_node.start_point[1]
        call_node = Node(
            id=_node_id(f"call:{call_name}", file_path, call_line, call_col),
            name=call_name,
            kind="call",
            file_path=file_path,
            language="java",
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

    def _handle_object_creation(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai `new Tipo(...)` como uma chamada ao construtor de `Tipo`.

        `new X()` é um nó de gramática à parte (`object_creation_expression`),
        não um `method_invocation` — sem isto, instanciações não apareceriam
        como chamadas, diferente de Python/Go/Rust onde `Tipo()` já é uma
        call_expression comum.
        """
        type_node = node.child_by_field_name("type")
        if type_node is None:
            return
        # `new HashMap<>()`: o campo 'type' é um 'generic_type' que engloba o
        # tipo em si e os argumentos genéricos ('<>') — desembrulha antes de
        # seguir. `new java.util.HashMap()`: o tipo vira 'scoped_type_identifier'
        # (caminho qualificado) — pega só o último segmento ('type_identifier'),
        # o nome simples. Sem isso o nome capturado seria "HashMap<>" ou
        # "java.util.HashMap" em vez de "HashMap".
        if type_node.type == "generic_type":
            inner = next(
                (c for c in type_node.children if c.type in ("type_identifier", "scoped_type_identifier")), None
            )
            if inner is not None:
                type_node = inner
        if type_node.type == "scoped_type_identifier":
            inner = next((c for c in type_node.children if c.type == "type_identifier"), None)
            if inner is not None:
                type_node = inner

        call_name = _get_text(source, type_node)
        call_line = type_node.start_point[0] + 1
        call_col = type_node.start_point[1]
        call_node = Node(
            id=_node_id(f"call:{call_name}", file_path, call_line, call_col),
            name=call_name,
            kind="call",
            file_path=file_path,
            language="java",
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
