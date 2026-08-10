"""Testes estendidos para parser C# — regressão de node_id e edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.parser.csharp import CSharpParser


@pytest.fixture
def parser() -> CSharpParser:
    """Parser C# para testes."""
    try:
        return CSharpParser()
    except RuntimeError:
        pytest.skip("tree-sitter-c-sharp não instalado")


class TestCSharpNodeIdDisambiguation:
    """Regressão: _node_id inclui coluna, e chamadas encadeadas ao mesmo
    método não colidem no mesmo id (mesma classe de defeito corrigida nos
    parsers Python, TypeScript, Go, Rust e Java)."""

    def test_same_name_same_line_distinct_columns_get_distinct_ids(self, parser: CSharpParser) -> None:
        """Dois métodos HOMÔNIMOS em classes distintas na mesma linha física.

        Nomes diferentes já produzem hashes diferentes mesmo sem a coluna,
        por incluírem o nome — só o mesmo nome na mesma linha física expõe
        se a coluna está de fato no cálculo do id.
        """
        source = "class A{void Mul(){}}class B{void Mul(){}}\n"
        nodes, _ = parser.parse_file(Path("Min.cs"), source)
        muls = [n for n in nodes if n.name == "Mul" and n.kind == "method"]
        assert len(muls) == 2
        assert muls[0].line_start == muls[1].line_start == 1
        assert muls[0].id != muls[1].id

    def test_chained_calls_to_same_method_get_distinct_ids(self, parser: CSharpParser) -> None:
        """"x.F().F()" — duas chamadas a `F` na mesma linha, receivers diferentes.

        A posição correta é a do nó do nome do método dentro do
        member_access_expression (o identificador do método), não a do
        invocation_expression inteiro (que para o segundo `.F()` da cadeia
        engloba a chamada anterior) — senão as duas chamadas a `F`
        colidiriam no mesmo id.
        """
        source = "class C { void Run() {\n  x.F().F();\n} }\n"
        nodes, _ = parser.parse_file(Path("Chain.cs"), source)
        calls = [n for n in nodes if n.kind == "call" and n.name == "F"]
        assert len(calls) == 2
        assert calls[0].id != calls[1].id


class TestCSharpParserEdgeCases:
    """Edge cases adicionais do parser C#."""

    def test_class_without_name_does_not_crash(self, parser: CSharpParser) -> None:
        """AST malformada (classe sem identificador) não deve crashar o parser."""
        source = "class { }\n"
        nodes, _ = parser.parse_file(Path("Bad.cs"), source)
        assert len(nodes) >= 1  # pelo menos o file node

    def test_nested_class_is_attached_to_outer_class(self, parser: CSharpParser) -> None:
        """Classe aninhada (inner class) deve ganhar 'contains' da classe externa."""
        source = """
class Outer {
    class Inner {
        void M() {}
    }
}
"""
        nodes, edges = parser.parse_file(Path("Outer.cs"), source)
        outer = next(n for n in nodes if n.kind == "class" and n.name == "Outer")
        inner = next(n for n in nodes if n.kind == "class" and n.name == "Inner")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == inner.id]
        assert len(contains) == 1
        assert contains[0].source_id == outer.id

    def test_multiple_classes_in_same_file(self, parser: CSharpParser) -> None:
        """Múltiplas classes top-level no mesmo arquivo são extraídas."""
        source = """
class A {}
class B {}
"""
        nodes, _ = parser.parse_file(Path("Main.cs"), source)
        classes = {n.name for n in nodes if n.kind == "class"}
        assert classes == {"A", "B"}

    def test_generic_class_declaration_does_not_crash(self, parser: CSharpParser) -> None:
        """Classe genérica (`class Box<T>`) não deve crashar o parser."""
        source = """
class Box<T> {
    T value;
    T Get() { return value; }
}
"""
        nodes, _ = parser.parse_file(Path("Box.cs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "Box"

    def test_namespace_declaration_is_not_a_class(self, parser: CSharpParser) -> None:
        """`namespace X { ... }` NÃO deve virar 'class' — só o que está dentro."""
        source = """
namespace MyApp.Models {
    class Dog {}
}
"""
        nodes, _ = parser.parse_file(Path("Dog.cs"), source)
        classes = {n.name for n in nodes if n.kind == "class"}
        assert classes == {"Dog"}

    def test_static_class_does_not_crash(self, parser: CSharpParser) -> None:
        """Classe estática (`static class X`) não deve crashar o parser."""
        source = """
static class Utils {
    public static int Add(int a, int b) { return a + b; }
}
"""
        nodes, _ = parser.parse_file(Path("Utils.cs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "Utils"
