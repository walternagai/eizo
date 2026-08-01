"""Testes estendidos para parser Java — regressão de node_id e edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.parser.java import JavaParser


@pytest.fixture
def parser() -> JavaParser:
    """Parser Java para testes."""
    try:
        return JavaParser()
    except RuntimeError:
        pytest.skip("tree-sitter-java não instalado")


class TestJavaNodeIdDisambiguation:
    """Regressão: _node_id inclui coluna, e chamadas encadeadas ao mesmo
    método não colidem no mesmo id (mesma classe de defeito corrigida nos
    parsers Python, TypeScript, Go e Rust)."""

    def test_same_name_same_line_distinct_columns_get_distinct_ids(self, parser: JavaParser) -> None:
        """Dois métodos HOMÔNIMOS em classes distintas na mesma linha física.

        Nomes diferentes já produzem hashes diferentes mesmo sem a coluna,
        por incluírem o nome — só o mesmo nome na mesma linha física expõe
        se a coluna está de fato no cálculo do id.
        """
        source = "class A{void mul(){}}class B{void mul(){}}\n"
        nodes, _ = parser.parse_file(Path("Min.java"), source)
        muls = [n for n in nodes if n.name == "mul" and n.kind == "method"]
        assert len(muls) == 2
        assert muls[0].line_start == muls[1].line_start == 1
        assert muls[0].id != muls[1].id

    def test_chained_calls_to_same_method_get_distinct_ids(self, parser: JavaParser) -> None:
        """"x.f().f()" — duas chamadas a `f` na mesma linha, receivers diferentes.

        A posição correta é a do campo "name" do method_invocation (o
        identificador do método), não a do nó inteiro (que para o segundo
        `.f()` da cadeia engloba a chamada anterior) — senão as duas
        chamadas a `f` colidiriam no mesmo id.
        """
        source = "class C { void run() {\n  x.f().f();\n} }\n"
        nodes, _ = parser.parse_file(Path("Chain.java"), source)
        calls = [n for n in nodes if n.kind == "call" and n.name == "f"]
        assert len(calls) == 2
        assert calls[0].id != calls[1].id


class TestJavaParserEdgeCases:
    """Edge cases adicionais do parser Java."""

    def test_class_without_name_does_not_crash(self, parser: JavaParser) -> None:
        """AST malformada (classe sem identificador) não deve crashar o parser."""
        source = "class { }\n"
        nodes, _ = parser.parse_file(Path("Bad.java"), source)
        assert len(nodes) >= 1  # pelo menos o file node

    def test_nested_class_is_attached_to_outer_class(self, parser: JavaParser) -> None:
        """Classe aninhada (inner class) deve ganhar 'contains' da classe externa."""
        source = """
class Outer {
    class Inner {
        void m() {}
    }
}
"""
        nodes, edges = parser.parse_file(Path("Outer.java"), source)
        outer = next(n for n in nodes if n.kind == "class" and n.name == "Outer")
        inner = next(n for n in nodes if n.kind == "class" and n.name == "Inner")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == inner.id]
        assert len(contains) == 1
        assert contains[0].source_id == outer.id

    def test_multiple_classes_in_same_file(self, parser: JavaParser) -> None:
        """Múltiplas classes top-level no mesmo arquivo (não-public) são extraídas."""
        source = """
class A {}
class B {}
"""
        nodes, _ = parser.parse_file(Path("Main.java"), source)
        classes = {n.name for n in nodes if n.kind == "class"}
        assert classes == {"A", "B"}

    def test_generic_class_declaration_does_not_crash(self, parser: JavaParser) -> None:
        """Classe genérica (`class Box<T>`) não deve crashar o parser."""
        source = """
class Box<T> {
    T value;
    T get() { return value; }
}
"""
        nodes, _ = parser.parse_file(Path("Box.java"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "Box"
