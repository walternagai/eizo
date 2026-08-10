"""Testes para parser/ruby.py."""

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


class TestRubyParser:
    """Testes para o parser Ruby."""

    def test_language_property(self, parser: RubyParser) -> None:
        """Propriedade language deve retornar 'ruby'."""
        assert parser.language == "ruby"

    def test_extensions(self, parser: RubyParser) -> None:
        """Extensões devem incluir .rb."""
        assert ".rb" in parser.extensions

    def test_parse_empty_file(self, parser: RubyParser) -> None:
        """Arquivo vazio deve retornar apenas o nó do arquivo."""
        nodes, edges = parser.parse_file(Path("Empty.rb"), "")
        assert len(nodes) >= 1
        assert nodes[0].kind == "file"

    def test_parse_class(self, parser: RubyParser) -> None:
        """Deve extrair definições de classe."""
        source = """
class Dog
  def bark
  end
end
"""
        nodes, edges = parser.parse_file(Path("dog.rb"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Dog"

    def test_parse_module_as_class(self, parser: RubyParser) -> None:
        """Módulo deve ser extraído como 'class' (análogo mais próximo)."""
        source = """
module MyApp
end
"""
        nodes, edges = parser.parse_file(Path("my_app.rb"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "MyApp"

    def test_parse_method_attached_to_class(self, parser: RubyParser) -> None:
        """Método deve virar 'method' com 'contains' a partir da classe."""
        source = """
class Dog
  def bark
  end
end
"""
        nodes, edges = parser.parse_file(Path("dog.rb"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "bark"

        dog = next(n for n in nodes if n.kind == "class")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == methods[0].id]
        assert len(contains) == 1
        assert contains[0].source_id == dog.id

    def test_parse_top_level_method(self, parser: RubyParser) -> None:
        """Método top-level (fora de classe) deve virar 'method'."""
        source = """
def top_level
  1
end
"""
        nodes, edges = parser.parse_file(Path("lib.rb"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "top_level"

    def test_parse_extends_creates_inherits_edge(self, parser: RubyParser) -> None:
        """`class X < Y` deve criar aresta 'inherits'."""
        source = """
class Dog < Animal
end
"""
        nodes, edges = parser.parse_file(Path("dog.rb"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].metadata.get("base_name") == "Animal"

    def test_parse_plain_call(self, parser: RubyParser) -> None:
        """Deve extrair chamada de método sem receiver explícito.

        Chamadas sem parênteses e sem receiver (`helper` solto) são
        'identifier' na gramática Ruby — só chamadas com parênteses ou
        receiver viram nó 'call' (quirk documentado no AGENTS.md).
        """
        source = """
def caller
  helper()
end
"""
        nodes, edges = parser.parse_file(Path("main.rb"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "helper" for c in calls)

    def test_parse_call_with_parentheses(self, parser: RubyParser) -> None:
        """Chamada com parênteses (helper()) deve extrair o nome."""
        source = """
def caller
  helper()
end
"""
        nodes, edges = parser.parse_file(Path("main.rb"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "helper" for c in calls)

    def test_parse_method_call_with_receiver(self, parser: RubyParser) -> None:
        """Chamada de método (obj.speak) deve extrair o nome do método."""
        source = """
def caller(obj)
  obj.speak
end
"""
        nodes, edges = parser.parse_file(Path("main.rb"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "speak" for c in calls)

    def test_parse_self_call(self, parser: RubyParser) -> None:
        """Chamada com self (self.helper) deve extrair o nome do método."""
        source = """
class Dog
  def run
    self.helper
  end
end
"""
        nodes, edges = parser.parse_file(Path("dog.rb"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "helper" for c in calls)

    def test_parse_nested_call_in_arguments(self, parser: RubyParser) -> None:
        """Chamada aninhada nos argumentos (outer(inner())) deve extrair ambas.

        `fetch` sem parênteses é 'identifier' solto na gramática Ruby — só
        as chamadas com parênteses (`process`, `transform`) viram 'call'.
        """
        source = """
def caller
  process(transform(fetch()))
end
"""
        nodes, edges = parser.parse_file(Path("main.rb"), source)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert call_names == {"process", "transform", "fetch"}
