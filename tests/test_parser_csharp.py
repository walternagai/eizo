"""Testes para parser/csharp.py."""

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


class TestCSharpParser:
    """Testes para o parser C#."""

    def test_language_property(self, parser: CSharpParser) -> None:
        """Propriedade language deve retornar 'csharp'."""
        assert parser.language == "csharp"

    def test_extensions(self, parser: CSharpParser) -> None:
        """Extensões devem incluir .cs."""
        assert ".cs" in parser.extensions

    def test_parse_empty_file(self, parser: CSharpParser) -> None:
        """Arquivo vazio deve retornar apenas o nó do arquivo."""
        nodes, edges = parser.parse_file(Path("Empty.cs"), "")
        assert len(nodes) >= 1
        assert nodes[0].kind == "file"

    def test_parse_class(self, parser: CSharpParser) -> None:
        """Deve extrair definições de classe."""
        source = """
class Dog {
    void Bark() {}
}
"""
        nodes, edges = parser.parse_file(Path("Dog.cs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Dog"

    def test_parse_interface_as_class(self, parser: CSharpParser) -> None:
        """Interface deve ser extraída como 'class'."""
        source = """
interface IAnimal {
    string Speak();
}
"""
        nodes, edges = parser.parse_file(Path("IAnimal.cs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "IAnimal"

    def test_parse_struct_as_class(self, parser: CSharpParser) -> None:
        """Struct deve ser extraída como 'class'."""
        source = """
struct Point {
    public int X;
}
"""
        nodes, edges = parser.parse_file(Path("Point.cs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Point"

    def test_parse_enum_as_class(self, parser: CSharpParser) -> None:
        """Enum deve ser extraído como 'class'."""
        source = """
enum Status {
    Ok, Err
}
"""
        nodes, edges = parser.parse_file(Path("Status.cs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Status"

    def test_parse_record_as_class(self, parser: CSharpParser) -> None:
        """Record (C# 9+) deve ser extraído como 'class'."""
        source = """
record Person(string Name);
"""
        nodes, edges = parser.parse_file(Path("Person.cs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Person"

    def test_parse_method_attached_to_class(self, parser: CSharpParser) -> None:
        """Método deve virar 'method' com 'contains' a partir da classe."""
        source = """
class Dog {
    void Bark() {}
}
"""
        nodes, edges = parser.parse_file(Path("Dog.cs"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "Bark"

        dog = next(n for n in nodes if n.kind == "class")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == methods[0].id]
        assert len(contains) == 1
        assert contains[0].source_id == dog.id

    def test_interface_abstract_method_has_no_body_but_is_extracted(self, parser: CSharpParser) -> None:
        """Método abstrato de interface (sem corpo) ainda vira 'method'."""
        source = """
interface IAnimal {
    string Speak();
}
"""
        nodes, edges = parser.parse_file(Path("IAnimal.cs"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "Speak"

    def test_parse_extends_creates_inherits_edge(self, parser: CSharpParser) -> None:
        """`class X : Y` deve criar aresta 'inherits'."""
        source = """
class Dog : Animal {
}
"""
        nodes, edges = parser.parse_file(Path("Dog.cs"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].metadata.get("base_name") == "Animal"

    def test_parse_multiple_base_types(self, parser: CSharpParser) -> None:
        """`class X : A, B` deve criar uma aresta 'inherits' por tipo base."""
        source = """
class Dog : Animal, IComparable {
}
"""
        nodes, edges = parser.parse_file(Path("Dog.cs"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        base_names = {e.metadata.get("base_name") for e in inherits}
        assert base_names == {"Animal", "IComparable"}

    def test_parse_generic_base_type(self, parser: CSharpParser) -> None:
        """`class X : List<T>` deve extrair o nome genérico como base."""
        source = """
class Box : List<Item> {
}
"""
        nodes, edges = parser.parse_file(Path("Box.cs"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].metadata.get("base_name") == "List<Item>"

    def test_parse_simple_using(self, parser: CSharpParser) -> None:
        """`using System;` simples."""
        source = "using System;\n"
        nodes, edges = parser.parse_file(Path("Main.cs"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"System"}

    def test_parse_qualified_using(self, parser: CSharpParser) -> None:
        """`using System.Collections.Generic;` deve extrair o caminho completo."""
        source = "using System.Collections.Generic;\n"
        nodes, edges = parser.parse_file(Path("Main.cs"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"System.Collections.Generic"}

    def test_parse_plain_call(self, parser: CSharpParser) -> None:
        """Deve extrair chamada de método sem receiver explícito."""
        source = """
class Main {
    void Caller() {
        Callee();
    }
}
"""
        nodes, edges = parser.parse_file(Path("Main.cs"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "Callee" for c in calls)

    def test_parse_method_call_with_receiver(self, parser: CSharpParser) -> None:
        """Chamada de método (obj.Metodo()) deve extrair o nome do método."""
        source = """
class Main {
    void Caller(Dog obj) {
        obj.Speak();
    }
}
"""
        nodes, edges = parser.parse_file(Path("Main.cs"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "Speak" for c in calls)

    def test_parse_object_creation_as_call(self, parser: CSharpParser) -> None:
        """`new Tipo()` deve virar uma chamada ao nome do tipo."""
        source = """
class Main {
    void Caller() {
        Dog d = new Dog();
    }
}
"""
        nodes, edges = parser.parse_file(Path("Main.cs"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "Dog" for c in calls)

    def test_parse_nested_call_in_arguments(self, parser: CSharpParser) -> None:
        """Chamada aninhada nos argumentos (Outer(Inner())) deve extrair ambas."""
        source = """
class Main {
    void Caller() {
        Process(Transform(Fetch()));
    }
}
"""
        nodes, edges = parser.parse_file(Path("Main.cs"), source)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert call_names == {"Process", "Transform", "Fetch"}
