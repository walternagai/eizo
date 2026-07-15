"""Parser Python usando Tree-sitter.

Extrai funções, classes, métodos, imports e chamadas de arquivos .py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

from eizo.graph.models import Edge, Node
from eizo.parser.base import BaseParser

# Carrega a linguagem Python do pacote tree-sitter-python
try:
    from tree_sitter_python import language as python_language

    _capsule = python_language()
    PYTHON_LANGUAGE: Language | None = Language(_capsule)
except ImportError:
    PYTHON_LANGUAGE = None


def _node_id(name: str, file_path: str, line: int) -> str:
    """Gera um ID único para um nó."""
    raw = f"{file_path}:{name}:{line}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_text(source: bytes, node: Any) -> str:
    """Extrai texto de um nó Tree-sitter."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_docstring(source: bytes, node: Any) -> str | None:
    """Tenta extrair docstring de um nó de função/classe."""
    try:
        body = node.child_by_field_name("body")
        if body is None or body.child_count == 0:
            return None
        first_stmt = body.child(0)
        if first_stmt is None:
            return None
        if first_stmt.type == "expression_statement":
            expr = first_stmt.child(0)
            if expr and expr.type == "string":
                text = _get_text(source, expr)
                # Remove aspas (simples, duplas, triplas)
                for quote in ('"""', "'''", '"', "'"):
                    if text.startswith(quote) and text.endswith(quote):
                        text = text[len(quote) : -len(quote)]
                        break
                return text.strip()
        return None
    except Exception:
        return None


class PythonParser(BaseParser):
    """Parser para Python."""

    @property
    def language(self) -> str:
        return "python"

    @property
    def extensions(self) -> set[str]:
        return {".py"}

    def __init__(self) -> None:
        if PYTHON_LANGUAGE is None:
            msg = (
                "tree-sitter-python não está instalado. "
                "Execute: pip install tree-sitter-python"
            )
            raise RuntimeError(msg)
        self._parser = Parser(PYTHON_LANGUAGE)

    def parse_file(self, file_path: Path, source: str) -> tuple[list[Node], list[Edge]]:
        """Parseia um arquivo Python."""
        source_bytes = source.encode("utf-8")
        tree = self._parser.parse(source_bytes)
        nodes: list[Node] = []
        edges: list[Edge] = []
        file_path_str = str(file_path)

        # Nó do arquivo
        file_node = Node(
            id=_node_id("__file__", file_path_str, 0),
            name=file_path.name,
            kind="file",
            file_path=file_path_str,
            language="python",
            line_start=1,
            line_end=source.count("\n") + 1,
        )
        nodes.append(file_node)

        # Percorre a AST
        self._walk_tree(
            tree.root_node,
            source_bytes,
            file_path_str,
            nodes,
            edges,
            file_node.id,
        )

        return nodes, edges

    def _walk_tree(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None = None,
    ) -> None:
        """Percorre a AST recursivamente extraindo símbolos."""
        node_type = node.type

        if node_type == "function_definition":
            self._handle_function(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "class_definition":
            self._handle_class(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "import_statement":
            self._handle_import(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "import_from_statement":
            self._handle_import_from(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "call":
            self._handle_call(node, source, file_path, nodes, edges, parent_id)
        else:
            # Continua recursão para nós não tratados
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id)

    def _handle_function(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai uma definição de função."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)
        docstring = _get_docstring(source, node)

        kind = "method" if parent_id and parent_id != _node_id("__file__", file_path, 0) else "function"

        func_node = Node(
            id=_node_id(name, file_path, start_line),
            name=name,
            kind=kind,
            file_path=file_path,
            language="python",
            line_start=start_line,
            line_end=end_line,
            docstring=docstring,
            code_snippet=code[:500],
        )
        nodes.append(func_node)

        if parent_id:
            edges.append(Edge(
                source_id=parent_id,
                target_id=func_node.id,
                kind="contains",
            ))

        # Continua dentro da função para calls
        for child in node.children:
            self._walk_tree(child, source, file_path, nodes, edges, func_node.id)

    def _handle_class(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai uma definição de classe."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)
        docstring = _get_docstring(source, node)

        class_node = Node(
            id=_node_id(name, file_path, start_line),
            name=name,
            kind="class",
            file_path=file_path,
            language="python",
            line_start=start_line,
            line_end=end_line,
            docstring=docstring,
            code_snippet=code[:500],
        )
        nodes.append(class_node)

        if parent_id:
            edges.append(Edge(
                source_id=parent_id,
                target_id=class_node.id,
                kind="contains",
            ))

        # Herança (campo 'superclasses' no tree-sitter Python)
        superclasses = node.child_by_field_name("superclasses")
        if superclasses:
            for base in superclasses.children:
                if base.type == "identifier":
                    base_name = _get_text(source, base)
                    base_line = base.start_point[0] + 1
                    base_id = _node_id(base_name, file_path, base_line)
                    # Cria nó stub para a classe base (pode estar em outro arquivo)
                    base_node = Node(
                        id=base_id,
                        name=base_name,
                        kind="class",
                        file_path=file_path,
                        language="python",
                        line_start=base_line,
                        line_end=base_line,
                        metadata={"external": True},
                    )
                    nodes.append(base_node)
                    edges.append(Edge(
                        source_id=class_node.id,
                        target_id=base_id,
                        kind="inherits",
                        metadata={"base_name": base_name},
                    ))

        # Continua dentro da classe para métodos
        for child in node.children:
            self._walk_tree(child, source, file_path, nodes, edges, class_node.id)

    def _handle_import(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai imports."""
        for child in node.children:
            if child.type == "dotted_name":
                module_name = _get_text(source, child)
                import_node = Node(
                    id=_node_id(f"import:{module_name}", file_path, child.start_point[0] + 1),
                    name=module_name,
                    kind="import",
                    file_path=file_path,
                    language="python",
                    line_start=child.start_point[0] + 1,
                    line_end=child.end_point[0] + 1,
                )
                nodes.append(import_node)
                if parent_id:
                    edges.append(Edge(
                        source_id=parent_id,
                        target_id=import_node.id,
                        kind="imports",
                    ))

    def _handle_import_from(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai imports do tipo 'from X import Y'."""
        module_node = node.child_by_field_name("module_name")
        if module_node is None:
            return

        module_name = _get_text(source, module_node)
        names = node.child_by_field_name("name")
        if names:
            for name_node in names.children:
                if name_node.type == "dotted_name":
                    name = _get_text(source, name_node)
                    import_node = Node(
                        id=_node_id(f"import:{module_name}.{name}", file_path, name_node.start_point[0] + 1),
                        name=f"{module_name}.{name}",
                        kind="import",
                        file_path=file_path,
                        language="python",
                        line_start=name_node.start_point[0] + 1,
                        line_end=name_node.end_point[0] + 1,
                    )
                    nodes.append(import_node)
                    if parent_id:
                        edges.append(Edge(
                            source_id=parent_id,
                            target_id=import_node.id,
                            kind="imports",
                        ))

    def _handle_call(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai chamadas de função."""
        func_node = node.child_by_field_name("function")
        if func_node is None:
            return

        # Pega o nome da função chamada
        if func_node.type == "identifier":
            call_name = _get_text(source, func_node)
        elif func_node.type == "attribute":
            # method calls: obj.method
            attr = func_node.child_by_field_name("attribute")
            if attr:
                call_name = _get_text(source, attr)
            else:
                return
        else:
            return

        call_line = func_node.start_point[0] + 1
        call_node = Node(
            id=_node_id(f"call:{call_name}", file_path, call_line),
            name=call_name,
            kind="call",
            file_path=file_path,
            language="python",
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
