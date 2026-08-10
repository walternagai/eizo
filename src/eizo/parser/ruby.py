"""Parser Ruby usando Tree-sitter.

Extrai classes e módulos (como 'class'), métodos (`def`), e chamadas de
arquivos .rb.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

from eizo.graph.models import Edge, Node
from eizo.parser.base import BaseParser

# Carrega a linguagem Ruby do pacote tree-sitter-ruby
try:
    from tree_sitter_ruby import language as ruby_language

    _capsule = ruby_language()
    RUBY_LANGUAGE: Language | None = Language(_capsule)
except ImportError:
    RUBY_LANGUAGE = None

# Nós Ruby que viram 'class' no grafo. `module` é o análogo mais próximo de
# classe em Ruby (o schema do grafo não tem kind 'module').
_TYPE_DECL_KINDS: frozenset[str] = frozenset({"class", "module"})
_METHOD_DECL_KINDS: frozenset[str] = frozenset({"method", "singleton_method"})
# Nós que representam o nome do tipo base no superclass (`class X < Y`).
_BASE_TYPE_KINDS: frozenset[str] = frozenset({"constant"})


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


class RubyParser(BaseParser):
    """Parser para Ruby."""

    @property
    def language(self) -> str:
        return "ruby"

    @property
    def extensions(self) -> set[str]:
        return {".rb"}

    def __init__(self) -> None:
        if RUBY_LANGUAGE is None:
            msg = "tree-sitter-ruby não está instalado. Execute: pip install tree-sitter-ruby"
            raise RuntimeError(msg)
        self._parser = Parser(RUBY_LANGUAGE)

    def parse_file(self, file_path: Path, source: str) -> tuple[list[Node], list[Edge]]:
        """Parseia um arquivo Ruby."""
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
            language="ruby",
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
        elif node_type == "call":
            self._handle_call(node, source, file_path, nodes, edges, parent_id)
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
        """Extrai `class`/`module` como 'class'.

        O nome é um nó 'constant' (não 'identifier' como nas outras
        linguagens). `class X < Y` tem um campo 'superclass' com o tipo base.
        """
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
            language="ruby",
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
        """Extrai o `superclass` (`class X < Y`) como aresta 'inherits'.

        O campo 'superclass' engloba o operador `<` e o nome do tipo base
        (um nó 'constant').
        """
        superclass = node.child_by_field_name("superclass")
        if superclass is None:
            return

        base = next((c for c in superclass.children if c.type in _BASE_TYPE_KINDS), None)
        if base is None:
            return

        base_name = _get_text(source, base)
        base_line = base.start_point[0] + 1
        base_col = base.start_point[1]
        base_id = _node_id(base_name, file_path, base_line, base_col)
        base_node = Node(
            id=base_id,
            name=base_name,
            kind="class",
            file_path=file_path,
            language="ruby",
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
        """Extrai método (`def`) como 'method'.

        Nomes Ruby podem terminar em `?`, `!` ou `=` (ex: `valid?`, `save!`,
        `name=`) — o texto do nó 'identifier' já inclui esses sufixos, então
        o nome é preservado intacto. Setters (`def name=(n)`) usam um nó
        'setter' em vez de 'identifier' — o texto do nó inteiro é o nome
        (`name=`).
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
            language="ruby",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(method_node)

        if parent_id:
            edges.append(Edge(source_id=parent_id, target_id=method_node.id, kind="contains"))

        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self._walk_tree(child, source, file_path, nodes, edges, method_node.id)

    def _handle_call(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai chamadas: `foo`, `foo()`, `obj.metodo` e `self.metodo`.

        O nó 'call' tem o nome do método como último filho 'identifier'
        (para `obj.metodo` o receiver é o primeiro filho; para `self.metodo`
        o receiver é o nó 'self'). A posição usada é a do nó do nome do
        método, não a do call inteiro (senão `x.f().f()` colidiria).
        """
        name_node = next(
            (c for c in reversed(node.children) if c.type == "identifier"), None
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
            language="ruby",
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
