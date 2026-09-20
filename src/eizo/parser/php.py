"""Parser PHP usando Tree-sitter.

Extrai classes/interfaces/traits/enums (como 'class'), métodos, funções
top-level, imports (`use`) e chamadas de arquivos .php.
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

# Carrega a linguagem PHP do pacote tree-sitter-php. Atenção: o pacote
# exporta `language_php` (e `language_php_only`), NÃO `language` como os
# demais pacotes tree-sitter-* — o import abaixo é o único ponto que difere
# do padrão dos outros parsers.
try:
    from tree_sitter_php import language_php as php_language

    _capsule = php_language()
    PHP_LANGUAGE: Language | None = Language(_capsule)
except ImportError:
    PHP_LANGUAGE = None

# Nós PHP que viram 'class' no grafo. PHP é AST-nested como Java: métodos
# ficam sintaticamente aninhados no corpo da declaração em todos os casos.
_TYPE_DECL_KINDS: frozenset[str] = frozenset({
    "class_declaration", "interface_declaration", "trait_declaration", "enum_declaration",
})
_METHOD_DECL_KINDS: frozenset[str] = frozenset({"method_declaration"})
# Nós que representam o nome do tipo base na base_clause/class_interface_clause.
_BASE_TYPE_KINDS: frozenset[str] = frozenset({"name", "qualified_name"})


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


class PhpParser(BaseParser):
    """Parser para PHP."""

    @property
    def language(self) -> str:
        return "php"

    @property
    def extensions(self) -> set[str]:
        return {".php"}

    def __init__(self) -> None:
        if PHP_LANGUAGE is None:
            msg = "tree-sitter-php não está instalado. Execute: pip install tree-sitter-php"
            raise RuntimeError(msg)
        self._parser = Parser(PHP_LANGUAGE)

    def parse_file(self, file_path: Path, source: str) -> tuple[list[Node], list[Edge]]:
        """Parseia um arquivo PHP."""
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
            language="php",
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
        elif node_type == "function_definition":
            self._handle_function(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "namespace_use_declaration":
            self._handle_use(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "function_call_expression":
            self._handle_call(node, source, file_path, nodes, edges, parent_id)
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id, _depth + 1)
        elif node_type == "member_call_expression":
            self._handle_member_call(node, source, file_path, nodes, edges, parent_id)
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
        """Extrai `class`/`interface`/`trait`/`enum` como 'class'."""
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
            language="php",
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
        """Extrai `extends` (base_clause) e `implements` (class_interface_clause)
        como arestas 'inherits'.

        A gramática PHP tem campos nomeados: 'base_clause' (extends) e
        'class_interface_clause' (implements). O nome do tipo base é um nó
        'name' (ou 'qualified_name' para `\\App\\Base`).
        """
        base_type_nodes: list[Any] = []

        base_clause = next((c for c in node.children if c.type == "base_clause"), None)
        if base_clause is not None:
            base_type_nodes.extend(c for c in base_clause.children if c.type in _BASE_TYPE_KINDS)

        class_interface_clause = next(
            (c for c in node.children if c.type == "class_interface_clause"), None
        )
        if class_interface_clause is not None:
            base_type_nodes.extend(
                c for c in class_interface_clause.children if c.type in _BASE_TYPE_KINDS
            )

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
                language="php",
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

        Sempre 'method': em PHP todo método vive dentro de um
        class/interface/trait/enum — funções soltas são `function_definition`
        (tratadas à parte).
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
            language="php",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(method_node)

        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=method_node.id, kind="contains"))

        # Métodos abstratos de interface (`public function speak();`) não têm body.
        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self._walk_tree(child, source, file_path, nodes, edges, method_node.id, 1)

    def _handle_function(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai função top-level (`function_definition`) como 'function'.

        A gramática PHP usa o mesmo nó `function_definition` para funções
        soltas e closures — closures não têm campo 'name' e são ignoradas
        (mesmo tradeoff dos demais parsers com lambdas).
        """
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        start_col = node.start_point[1]
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)

        function_node = Node(
            id=_node_id(name, file_path, start_line, start_col),
            name=name,
            kind="function",
            file_path=file_path,
            language="php",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(function_node)

        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=function_node.id, kind="contains"))

        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self._walk_tree(child, source, file_path, nodes, edges, function_node.id, 1)

    def _handle_use(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai `use X;` como import.

        O caminho é um 'qualified_name' dentro de um 'namespace_use_clause'
        (ex: `use App\\Models\\Dog;`). `use function ...` e `use const ...`
        também caem aqui — o qualified_name é o mesmo.
        """
        clause = next((c for c in node.children if c.type == "namespace_use_clause"), None)
        if clause is None:
            return
        path_node = next(
            (c for c in clause.children if c.type in ("qualified_name", "name")), None
        )
        if path_node is None:
            return

        import_path = _get_text(source, path_node)
        import_node = Node(
            id=_node_id(f"import:{import_path}", file_path, path_node.start_point[0] + 1, path_node.start_point[1]),
            name=import_path,
            kind="import",
            file_path=file_path,
            language="php",
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
        """Extrai chamada de função: `foo()`.

        O campo 'function' do function_call_expression é o nome da função
        chamada (pode ser 'name' ou 'qualified_name' para `\\App\\foo()`).
        """
        name_node = node.child_by_field_name("function")
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
            language="php",
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

    def _handle_member_call(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai chamada de método: `$obj->metodo()`.

        O nome do método é o último filho 'name' do member_call_expression
        (o receiver é o variable_name). A posição usada é a do nó do nome do
        método, não a do member_call inteiro.
        """
        name_node = next(
            (c for c in reversed(node.children) if c.type in ("name", "qualified_name")), None
        )
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
            language="php",
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
        não um function_call_expression — sem isto, instanciações não
        apareceriam como chamadas, diferente de Python/Go/Rust onde `Tipo()`
        já é uma call_expression comum. O tipo é o filho posicional 'name'
        (a gramática não dá field name a ele).
        """
        type_node = next((c for c in node.children if c.type in ("name", "qualified_name")), None)
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
            language="php",
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
