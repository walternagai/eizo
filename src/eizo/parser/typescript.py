"""Parser TypeScript/JavaScript usando Tree-sitter.

Extrai funções, classes, métodos, imports e chamadas de arquivos .ts/.tsx/.js/.jsx.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

from eizo.graph.models import Edge, Node
from eizo.parser.base import BaseParser

# Carrega a linguagem TypeScript do pacote tree-sitter-typescript
try:
    from tree_sitter_typescript import language_typescript as ts_language

    _capsule = ts_language()
    TS_LANGUAGE: Language | None = Language(_capsule)
except ImportError:
    TS_LANGUAGE = None


def _node_id(name: str, file_path: str, line: int) -> str:
    """Gera um ID único para um nó."""
    raw = f"{file_path}:{name}:{line}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_text(source: bytes, node: Any) -> str:
    """Extrai texto de um nó Tree-sitter."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


class TypeScriptParser(BaseParser):
    """Parser para TypeScript/JavaScript."""

    @property
    def language(self) -> str:
        return "typescript"

    @property
    def extensions(self) -> set[str]:
        return {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

    def __init__(self) -> None:
        if TS_LANGUAGE is None:
            msg = (
                "tree-sitter-typescript não está instalado. "
                "Execute: pip install tree-sitter-typescript"
            )
            raise RuntimeError(msg)
        self._parser = Parser(TS_LANGUAGE)

    def parse_file(self, file_path: Path, source: str) -> tuple[list[Node], list[Edge]]:
        """Parseia um arquivo TypeScript/JavaScript."""
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
            language="typescript",
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

        if node_type in ("function_declaration", "function"):
            self._handle_function(node, source, file_path, nodes, edges, parent_id)
        elif node_type in ("method_definition", "method"):
            self._handle_method(node, source, file_path, nodes, edges, parent_id)
        elif node_type in ("class_declaration", "class"):
            self._handle_class(node, source, file_path, nodes, edges, parent_id)
        elif node_type in ("arrow_function",):
            # Arrow functions anônimas — só extrai se tiver nome via assignment
            pass
        elif node_type in ("import_statement", "import"):
            self._handle_import(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "call_expression":
            self._handle_call(node, source, file_path, nodes, edges, parent_id)
        elif node_type == "export_statement":
            # Export statement pode conter declarações
            for child in node.children:
                self._walk_tree(child, source, file_path, nodes, edges, parent_id)
        else:
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
        """Extrai uma declaração de função."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)

        func_node = Node(
            id=_node_id(name, file_path, start_line),
            name=name,
            kind="function",
            file_path=file_path,
            language="typescript",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(func_node)

        if parent_id:
            edges.append(Edge(
                source_id=parent_id,
                target_id=func_node.id,
                kind="contains",
            ))

        for child in node.children:
            self._walk_tree(child, source, file_path, nodes, edges, func_node.id)

    def _handle_method(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai uma definição de método."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)

        method_node = Node(
            id=_node_id(name, file_path, start_line),
            name=name,
            kind="method",
            file_path=file_path,
            language="typescript",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(method_node)

        if parent_id:
            edges.append(Edge(
                source_id=parent_id,
                target_id=method_node.id,
                kind="contains",
            ))

        for child in node.children:
            self._walk_tree(child, source, file_path, nodes, edges, method_node.id)

    def _handle_class(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
        parent_id: str | None,
    ) -> None:
        """Extrai uma declaração de classe."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = _get_text(source, name_node)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = _get_text(source, node)

        class_node = Node(
            id=_node_id(name, file_path, start_line),
            name=name,
            kind="class",
            file_path=file_path,
            language="typescript",
            line_start=start_line,
            line_end=end_line,
            code_snippet=code[:500],
        )
        nodes.append(class_node)

        if parent_id:
            edges.append(Edge(
                source_id=parent_id,
                target_id=class_node.id,
                kind="contains",
            ))

        # Herança
        for child in node.children:
            if child.type == "class_heritage":
                for clause in child.children:
                    if clause.type == "extends_clause":
                        for base_child in clause.children:
                            if base_child.type in ("identifier", "type_identifier"):
                                base_name = _get_text(source, base_child)
                                base_id = _node_id(base_name, file_path, base_child.start_point[0] + 1)
                                edges.append(Edge(
                                    source_id=class_node.id,
                                    target_id=base_id,
                                    kind="inherits",
                                    metadata={"base_name": base_name},
                                ))

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
        source_node = node.child_by_field_name("source")
        if source_node is None:
            return

        module_name = _get_text(source, source_node).strip("'\"")
        import_node = Node(
            id=_node_id(f"import:{module_name}", file_path, source_node.start_point[0] + 1),
            name=module_name,
            kind="import",
            file_path=file_path,
            language="typescript",
            line_start=source_node.start_point[0] + 1,
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

        if func_node.type == "identifier":
            call_name = _get_text(source, func_node)
        elif func_node.type == "member_expression":
            prop = func_node.child_by_field_name("property")
            if prop:
                call_name = _get_text(source, prop)
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
            language="typescript",
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
