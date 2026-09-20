"""Parser C# usando Tree-sitter.

Extrai classes/interfaces/structs/enums/records (como 'class'), métodos,
imports (`using`) e chamadas de arquivos .cs.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

from eizo.graph.models import Edge, Node
from eizo.parser.base import MAX_AST_DEPTH, BaseParser

logger = logging.getLogger("eizo")

# Carrega a linguagem C# do pacote tree-sitter-c-sharp
try:
    from tree_sitter_c_sharp import language as csharp_language

    _capsule = csharp_language()
    CSHARP_LANGUAGE: Language | None = Language(_capsule)
except ImportError:
    CSHARP_LANGUAGE = None

# Nós C# que viram 'class' no grafo. C# é AST-nested como Java: métodos
# ficam sintaticamente aninhados no corpo da declaração em todos os casos,
# sem o problema de impl/receiver de Go/Rust.
_TYPE_DECL_KINDS: frozenset[str] = frozenset({
    "class_declaration", "interface_declaration", "struct_declaration",
    "enum_declaration", "record_declaration",
})
_METHOD_DECL_KINDS: frozenset[str] = frozenset({"method_declaration"})
# Nós que representam o tipo base na base_list: a gramática C# usa
# 'identifier' (não 'type_identifier' como Java) para o nome do tipo base.
_BASE_TYPE_KINDS: frozenset[str] = frozenset({"identifier", "generic_name"})


def _node_id(name: str, file_path: str, line: int, column: int = 0) -> str:
    """Gera um ID único para um nó.

    Inclui a coluna além da linha: arquivos gerados/minificados podem colocar
    múltiplos símbolos na mesma linha — "arquivo:nome:linha" sozinho colidiria
    entre eles (mesma correção aplicada aos demais parsers).
    """
    raw = f"{file_path}:{name}:{line}:{column}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_text(source: bytes, node: Any) -> str:
    """Extrai texto de um nó Tree-sitter."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


class CSharpParser(BaseParser):
    """Parser para C#."""

    @property
    def language(self) -> str:
        return "csharp"

    @property
    def extensions(self) -> set[str]:
        return {".cs"}

    def __init__(self) -> None:
        if CSHARP_LANGUAGE is None:
            msg = "tree-sitter-c-sharp não está instalado. Execute: pip install tree-sitter-c-sharp"
            raise RuntimeError(msg)
        self._parser = Parser(CSHARP_LANGUAGE)

    def parse_file(self, file_path: Path, source: str) -> tuple[list[Node], list[Edge]]:
        """Parseia um arquivo C#."""
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
            language="csharp",
            line_start=1,
            line_end=source.count("\n") + 1,
        )
        nodes.append(file_node)

        # RecursionError de aninhamento profundo vira parse PARCIAL (o que
        # já foi extraído até estourar a pilha fica) — o mesmo contrato
        # "nunca levanta exceção" do fuzz suite.
        try:
            self._walk_tree(tree.root_node, source_bytes, file_path_str, nodes, edges, file_node.id)
        except RecursionError:
            logger.warning(
                "Profundidade da AST excedeu o limite de recursão em %s — "
                "símbolos extraídos até aqui foram preservados (parse parcial).",
                file_path_str,
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
        _depth: int = 0,
    ) -> None:
        """Percorre a AST recursivamente extraindo símbolos.

        Guard contra RecursionError em input válido profundamente aninhado:
        ao passar de `MAX_AST_DEPTH` (ver parser/base.py), o walker para de
        descer — parse PARCIAL em vez de estourar a pilha e descartar o
        arquivo inteiro. O mesmo contrato "nunca levanta exceção" do fuzz
        suite.
        """
        if _depth > MAX_AST_DEPTH:
            return
        node_type = node.type

        if node_type in _TYPE_DECL_KINDS:
            self._handle_type_decl(node, source, file_path, nodes, edges, parent_id)
        elif node_type in _METHOD_DECL_KINDS:
            self._handle_method(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "using_directive":
            self._handle_using(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "invocation_expression":
            self._handle_invocation(node, source, file_path, nodes, edges, parent_id)
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id, _depth + 1)
        elif node_type == "object_creation_expression":
            self._handle_object_creation(node, source, file_path, nodes, edges, parent_id)
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id, _depth + 1)
        else:
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id, _depth + 1)

    def _handle_type_decl(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai `class`/`interface`/`struct`/`enum`/`record` como 'class'."""
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
            language="csharp",
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
                self._walk_tree(child, source, file_path, nodes, edges, class_node.id, 1)

    def _handle_inheritance(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        class_id: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        """Extrai a `base_list` (`class X : A, B`) como arestas 'inherits'.

        A gramática C# não tem campos nomeados 'superclass'/'interfaces' como
        Java — a base_list é um nó único cujos filhos diretos são os nomes
        dos tipos base (identifier ou generic_name, ex: `List<T>`).
        """
        base_list = next((c for c in node.children if c.type == "base_list"), None)
        if base_list is None:
            return

        for base in base_list.children:
            if base.type not in _BASE_TYPE_KINDS:
                continue
            base_name = _get_text(source, base)
            base_line = base.start_point[0] + 1
            base_col = base.start_point[1]
            base_id = _node_id(base_name, file_path, base_line, base_col)
            base_node = Node(
                id=base_id,
                name=base_name,
                kind="class",
                file_path=file_path,
                language="csharp",
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
        """Extrai método (`method_declaration`) como 'method'.

        Sempre 'method': em C# todo método vive dentro de um
        class/interface/struct/enum/record — não existe função top-level
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
            language="csharp",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(method_node)

        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=method_node.id, kind="contains"))

        # Métodos abstratos de interface (`string Speak();`) não têm body.
        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self._walk_tree(child, source, file_path, nodes, edges, method_node.id, 1)

    def _handle_using(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai `using X;` como import.

        O caminho pode ser um 'identifier' simples (`using System;`) ou um
        'qualified_name' (`using System.Collections.Generic;`).
        """
        path_node = next(
            (c for c in node.children if c.type in ("identifier", "qualified_name")), None
        )
        if path_node is None:
            return

        import_path = _get_text(source, path_node)
        import_node = Node(
            id=_node_id(f"import:{import_path}", file_path, path_node.start_point[0] + 1, path_node.start_point[1]),
            name=import_path,
            kind="import",
            file_path=file_path,
            language="csharp",
            line_start=path_node.start_point[0] + 1,
            line_end=path_node.end_point[0] + 1,
        )
        nodes.append(import_node)
        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=import_node.id, kind="imports"))

    def _handle_invocation(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai chamadas: `f()` e `obj.metodo()`.

        O campo 'function' do invocation_expression é um 'identifier' para
        chamada simples ou um 'member_access_expression' para `obj.metodo()`
        — neste caso o nome do método é o último 'identifier' do nó (o
        receiver é o primeiro). A posição usada é a do nó do nome do método,
        não a do invocation inteiro (senão `x.f().f()` colidiria).
        """
        function_node = node.child_by_field_name("function")
        if function_node is None:
            return

        if function_node.type == "member_access_expression":
            name_node = next(
                (c for c in reversed(function_node.children) if c.type == "identifier"), None
            )
        else:
            name_node = function_node
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
            language="csharp",
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
        não um `invocation_expression` — sem isto, instanciações não
        apareceriam como chamadas, diferente de Python/Go/Rust onde `Tipo()`
        já é uma call_expression comum.
        """
        type_node = node.child_by_field_name("type")
        if type_node is None:
            return

        call_name = _get_text(source, type_node)
        call_line = type_node.start_point[0] + 1
        call_col = type_node.start_point[1]
        call_node = Node(
            id=_node_id(f"call:{call_name}", file_path, call_line, call_col),
            name=call_name,
            kind="call",
            file_path=file_path,
            language="csharp",
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
