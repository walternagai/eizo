"""Testes para parser/java.py."""

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


class TestJavaParser:
    """Testes para o parser Java."""

    def test_language_property(self, parser: JavaParser) -> None:
        """Propriedade language deve retornar 'java'."""
        assert parser.language == "java"

    def test_extensions(self, parser: JavaParser) -> None:
        """Extensões devem incluir .java."""
        assert ".java" in parser.extensions

    def test_parse_empty_file(self, parser: JavaParser) -> None:
        """Arquivo vazio deve retornar apenas o nó do arquivo."""
        nodes, edges = parser.parse_file(Path("Empty.java"), "")
        assert len(nodes) >= 1
        assert nodes[0].kind == "file"

    def test_parse_class(self, parser: JavaParser) -> None:
        """Deve extrair definições de classe."""
        source = """
class Dog {
    void bark() {}
}
"""
        nodes, edges = parser.parse_file(Path("Dog.java"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Dog"

    def test_parse_interface_as_class(self, parser: JavaParser) -> None:
        """Interface deve ser extraída como 'class'."""
        source = """
interface Animal {
    String speak();
}
"""
        nodes, edges = parser.parse_file(Path("Animal.java"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Animal"

    def test_parse_enum_as_class(self, parser: JavaParser) -> None:
        """Enum deve ser extraído como 'class'."""
        source = """
enum Status {
    OK, ERR;
}
"""
        nodes, edges = parser.parse_file(Path("Status.java"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Status"

    def test_parse_record_as_class(self, parser: JavaParser) -> None:
        """Record (Java 14+) deve ser extraído como 'class'."""
        source = """
record Point(int x, int y) {
    void show() {}
}
"""
        nodes, edges = parser.parse_file(Path("Point.java"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Point"

    def test_parse_method_attached_to_class(self, parser: JavaParser) -> None:
        """Método deve virar 'method' com 'contains' a partir da classe."""
        source = """
class Dog {
    void bark() {}
}
"""
        nodes, edges = parser.parse_file(Path("Dog.java"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "bark"

        dog = next(n for n in nodes if n.kind == "class")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == methods[0].id]
        assert len(contains) == 1
        assert contains[0].source_id == dog.id

    def test_parse_constructor_as_method(self, parser: JavaParser) -> None:
        """Construtor deve virar 'method'."""
        source = """
class Dog {
    public Dog(String name) {}
}
"""
        nodes, edges = parser.parse_file(Path("Dog.java"), source)
        methods = [n for n in nodes if n.kind == "method" and n.name == "Dog"]
        assert len(methods) == 1

    def test_interface_abstract_method_has_no_body_but_is_extracted(self, parser: JavaParser) -> None:
        """Método abstrato de interface (sem corpo) ainda vira 'method'."""
        source = """
interface Animal {
    String speak();
}
"""
        nodes, edges = parser.parse_file(Path("Animal.java"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "speak"

    def test_parse_extends_creates_inherits_edge(self, parser: JavaParser) -> None:
        """`class X extends Y` deve criar aresta 'inherits'."""
        source = """
class Dog extends Animal {
}
"""
        nodes, edges = parser.parse_file(Path("Dog.java"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].metadata.get("base_name") == "Animal"

    def test_parse_implements_multiple_interfaces(self, parser: JavaParser) -> None:
        """`class X implements A, B` deve criar uma aresta 'inherits' por interface."""
        source = """
class Dog implements Comparable, Serializable {
}
"""
        nodes, edges = parser.parse_file(Path("Dog.java"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        base_names = {e.metadata.get("base_name") for e in inherits}
        assert base_names == {"Comparable", "Serializable"}

    def test_parse_interface_extends_multiple_interfaces(self, parser: JavaParser) -> None:
        """`interface X extends A, B` deve criar uma aresta 'inherits' por interface."""
        source = """
interface X extends A, B {
}
"""
        nodes, edges = parser.parse_file(Path("X.java"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        base_names = {e.metadata.get("base_name") for e in inherits}
        assert base_names == {"A", "B"}

    def test_parse_extends_and_implements_together(self, parser: JavaParser) -> None:
        """`class X extends Y implements A` deve criar arestas para ambos."""
        source = """
class Dog extends Animal implements Comparable {
}
"""
        nodes, edges = parser.parse_file(Path("Dog.java"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        base_names = {e.metadata.get("base_name") for e in inherits}
        assert base_names == {"Animal", "Comparable"}

    def test_parse_simple_import(self, parser: JavaParser) -> None:
        """`import java.util.List;` simples."""
        source = "import java.util.List;\n"
        nodes, edges = parser.parse_file(Path("Main.java"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"java.util.List"}

    def test_parse_wildcard_import(self, parser: JavaParser) -> None:
        """`import java.util.*;` deve extrair com sufixo '.*'."""
        source = "import java.util.*;\n"
        nodes, edges = parser.parse_file(Path("Main.java"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"java.util.*"}

    def test_parse_static_import(self, parser: JavaParser) -> None:
        """`import static X.Y.z;` deve extrair o caminho completo."""
        source = "import static java.lang.Math.max;\n"
        nodes, edges = parser.parse_file(Path("Main.java"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"java.lang.Math.max"}

    def test_parse_plain_call(self, parser: JavaParser) -> None:
        """Deve extrair chamada de método sem receiver explícito."""
        source = """
class Main {
    void caller() {
        callee();
    }
}
"""
        nodes, edges = parser.parse_file(Path("Main.java"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "callee" for c in calls)

    def test_parse_method_call_with_receiver(self, parser: JavaParser) -> None:
        """Chamada de método (obj.metodo()) deve extrair o nome do método."""
        source = """
class Main {
    void caller(Dog obj) {
        obj.speak();
    }
}
"""
        nodes, edges = parser.parse_file(Path("Main.java"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "speak" for c in calls)

    def test_parse_object_creation_as_call(self, parser: JavaParser) -> None:
        """`new Tipo(...)` deve virar uma chamada ao nome do tipo."""
        source = """
class Main {
    void caller() {
        Dog d = new Dog();
    }
}
"""
        nodes, edges = parser.parse_file(Path("Main.java"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "Dog" for c in calls)

    def test_parse_generic_object_creation_strips_type_arguments(self, parser: JavaParser) -> None:
        """`new HashMap<>()` deve virar chamada a 'HashMap', sem os '<>' no nome."""
        source = """
class Main {
    void caller() {
        java.util.Map<String, Integer> m = new java.util.HashMap<>();
    }
}
"""
        nodes, edges = parser.parse_file(Path("Main.java"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "HashMap" for c in calls)
        assert not any("<" in c.name for c in calls)

    def test_parse_nested_call_in_arguments(self, parser: JavaParser) -> None:
        """Chamada aninhada nos argumentos (outer(inner())) deve extrair ambas."""
        source = """
class Main {
    void caller() {
        process(transform(fetch()));
    }
}
"""
        nodes, edges = parser.parse_file(Path("Main.java"), source)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert call_names == {"process", "transform", "fetch"}
