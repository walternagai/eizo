"""Testes estendidos para parser Ruby — regressão de node_id e edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.parser.ruby import RubyParser


@pytest.fixture
def parser() -> RubyParser:
    """Parser Ruby para testes."""
    try:
        return RubyParser()
    except RuntimeError:
        pytest.skip("tree-sitter-ruby não instalado")


class TestRubyNodeIdDisambiguation:
    """Regressão: _node_id inclui coluna, e chamadas encadeadas ao mesmo
    método não colidem no mesmo id (mesma classe de defeito corrigida nos
    parsers Python, TypeScript, Go, Rust e Java)."""

    def test_same_name_same_line_distinct_columns_get_distinct_ids(self, parser: RubyParser) -> None:
        """Dois métodos HOMÔNIMOS em classes distintas na mesma linha física.

        Nomes diferentes já produzem hashes diferentes mesmo sem a coluna,
        por incluírem o nome — só o mesmo nome na mesma linha física expõe
        se a coluna está de fato no cálculo do id.
        """
        source = "class A;def mul;end;end;class B;def mul;end;end\n"
        nodes, _ = parser.parse_file(Path("Min.rb"), source)
        muls = [n for n in nodes if n.name == "mul" and n.kind == "method"]
        assert len(muls) == 2
        assert muls[0].line_start == muls[1].line_start == 1
        assert muls[0].id != muls[1].id

    def test_chained_calls_to_same_method_get_distinct_ids(self, parser: RubyParser) -> None:
        """"x.f.f" — duas chamadas a `f` na mesma linha, receivers diferentes.

        A posição correta é a do nó do nome do método dentro do nó 'call'
        (o identificador do método), não a do call inteiro (que para o
        segundo `.f` da cadeia engloba a chamada anterior) — senão as duas
        chamadas a `f` colidiriam no mesmo id.
        """
        source = "def run\n  x.f.f\nend\n"
        nodes, _ = parser.parse_file(Path("Chain.rb"), source)
        calls = [n for n in nodes if n.kind == "call" and n.name == "f"]
        assert len(calls) == 2
        assert calls[0].id != calls[1].id


class TestRubyParserEdgeCases:
    """Edge cases adicionais do parser Ruby."""

    def test_class_without_name_does_not_crash(self, parser: RubyParser) -> None:
        """AST malformada (classe sem nome) não deve crashar o parser."""
        source = "class\nend\n"
        nodes, _ = parser.parse_file(Path("Bad.rb"), source)
        assert len(nodes) >= 1  # pelo menos o file node

    def test_nested_class_is_attached_to_outer_class(self, parser: RubyParser) -> None:
        """Classe aninhada deve ganhar 'contains' da classe externa."""
        source = """
class Outer
  class Inner
    def m
    end
  end
end
"""
        nodes, edges = parser.parse_file(Path("outer.rb"), source)
        outer = next(n for n in nodes if n.kind == "class" and n.name == "Outer")
        inner = next(n for n in nodes if n.kind == "class" and n.name == "Inner")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == inner.id]
        assert len(contains) == 1
        assert contains[0].source_id == outer.id

    def test_multiple_classes_in_same_file(self, parser: RubyParser) -> None:
        """Múltiplas classes top-level no mesmo arquivo são extraídas."""
        source = """
class A
end
class B
end
"""
        nodes, _ = parser.parse_file(Path("main.rb"), source)
        classes = {n.name for n in nodes if n.kind == "class"}
        assert classes == {"A", "B"}

    def test_module_nested_in_module(self, parser: RubyParser) -> None:
        """Módulo aninhado em módulo deve ganhar 'contains' do módulo externo."""
        source = """
module Outer
  module Inner
  end
end
"""
        nodes, edges = parser.parse_file(Path("outer.rb"), source)
        outer = next(n for n in nodes if n.kind == "class" and n.name == "Outer")
        inner = next(n for n in nodes if n.kind == "class" and n.name == "Inner")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == inner.id]
        assert len(contains) == 1
        assert contains[0].source_id == outer.id

    def test_predicate_method_name_with_question_mark(self, parser: RubyParser) -> None:
        """Método com `?` no nome (`valid?`) deve preservar o nome completo."""
        source = """
class Dog
  def valid?
    true
  end
end
"""
        nodes, _ = parser.parse_file(Path("dog.rb"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "valid?"

    def test_bang_method_name_with_exclamation(self, parser: RubyParser) -> None:
        """Método com `!` no nome (`save!`) deve preservar o nome completo."""
        source = """
class Dog
  def save!
    true
  end
end
"""
        nodes, _ = parser.parse_file(Path("dog.rb"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "save!"

    def test_setter_method_name_with_equals(self, parser: RubyParser) -> None:
        """Setter (`def name=(n)`) deve preservar o nome completo `name=`."""
        source = """
class Dog
  def name=(n)
    @name = n
  end
end
"""
        nodes, _ = parser.parse_file(Path("dog.rb"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "name="

    def test_singleton_method_is_extracted(self, parser: RubyParser) -> None:
        """Método de classe (`def self.build`) deve virar 'method'."""
        source = """
class Dog
  def self.build
    new
  end
end
"""
        nodes, _ = parser.parse_file(Path("dog.rb"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "build"
