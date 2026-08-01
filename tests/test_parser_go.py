"""Testes para parser/go.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.parser.go import GoParser


@pytest.fixture
def parser() -> GoParser:
    """Parser Go para testes."""
    try:
        return GoParser()
    except RuntimeError:
        pytest.skip("tree-sitter-go não instalado")


class TestGoParser:
    """Testes para o parser Go."""

    def test_language_property(self, parser: GoParser) -> None:
        """Propriedade language deve retornar 'go'."""
        assert parser.language == "go"

    def test_extensions(self, parser: GoParser) -> None:
        """Extensões devem incluir .go."""
        assert ".go" in parser.extensions

    def test_parse_empty_file(self, parser: GoParser) -> None:
        """Arquivo vazio deve retornar apenas o nó do arquivo."""
        nodes, edges = parser.parse_file(Path("empty.go"), "")
        assert len(nodes) >= 1
        assert nodes[0].kind == "file"

    def test_parse_function(self, parser: GoParser) -> None:
        """Deve extrair funções top-level."""
        source = """
package main

func hello(name string) string {
    return "Hello, " + name
}
"""
        nodes, edges = parser.parse_file(Path("main.go"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "hello"

    def test_parse_struct_as_class(self, parser: GoParser) -> None:
        """Struct deve ser extraído como 'class'."""
        source = """
package main

type Dog struct {
    Name string
}
"""
        nodes, edges = parser.parse_file(Path("model.go"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Dog"

    def test_parse_interface_as_class(self, parser: GoParser) -> None:
        """Interface deve ser extraída como 'class'."""
        source = """
package main

type Animal interface {
    Speak() string
}
"""
        nodes, edges = parser.parse_file(Path("model.go"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Animal"

    def test_type_alias_not_extracted_as_class(self, parser: GoParser) -> None:
        """`type ID = string` (alias simples) não vira 'class'."""
        source = """
package main

type ID = string
"""
        nodes, edges = parser.parse_file(Path("main.go"), source)
        assert not any(n.kind == "class" for n in nodes)

    def test_parse_method_attached_to_receiver_struct(self, parser: GoParser) -> None:
        """Método deve virar 'method' e ganhar 'contains' a partir do struct receiver."""
        source = """
package main

type Dog struct {
    Name string
}

func (d *Dog) Speak() string {
    return d.Name
}
"""
        nodes, edges = parser.parse_file(Path("model.go"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "Speak"

        dog = next(n for n in nodes if n.kind == "class" and n.name == "Dog")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == methods[0].id]
        assert len(contains) == 1
        assert contains[0].source_id == dog.id

    def test_method_receiver_struct_declared_after_method(self, parser: GoParser) -> None:
        """A ordem entre `func (r T) M()` e `type T struct{}` no arquivo não importa."""
        source = """
package main

func (d *Dog) Speak() string {
    return d.Name
}

type Dog struct {
    Name string
}
"""
        nodes, edges = parser.parse_file(Path("model.go"), source)
        method = next(n for n in nodes if n.kind == "method" and n.name == "Speak")
        dog = next(n for n in nodes if n.kind == "class" and n.name == "Dog")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == method.id]
        assert len(contains) == 1
        assert contains[0].source_id == dog.id

    def test_embedded_struct_field_is_inherits_edge(self, parser: GoParser) -> None:
        """Campo embutido (sem nome próprio) vira aresta 'inherits'."""
        source = """
package main

type Animal struct {
    Name string
}

type Dog struct {
    Animal
    Breed string
}
"""
        nodes, edges = parser.parse_file(Path("model.go"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].metadata.get("base_name") == "Animal"

    def test_named_field_is_not_inherits_edge(self, parser: GoParser) -> None:
        """Campo normal com nome (mesmo que o tipo exista como struct) não é embedding."""
        source = """
package main

type Animal struct {
    Name string
}

type Dog struct {
    Pet Animal
}
"""
        nodes, edges = parser.parse_file(Path("model.go"), source)
        assert not any(e.kind == "inherits" for e in edges)

    def test_parse_imports(self, parser: GoParser) -> None:
        """Deve extrair imports, incluindo alias e blank import."""
        source = """
package main

import (
    "fmt"
    f "os"
    _ "net/http"
)
"""
        nodes, edges = parser.parse_file(Path("main.go"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"fmt", "os", "net/http"}

    def test_parse_plain_call(self, parser: GoParser) -> None:
        """Deve extrair chamada de função simples."""
        source = """
package main

func caller() {
    callee(42)
}
"""
        nodes, edges = parser.parse_file(Path("main.go"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert len(calls) >= 1
        assert calls[0].name == "callee"

    def test_parse_method_call(self, parser: GoParser) -> None:
        """Chamada de método (obj.Metodo()) deve extrair o nome do método."""
        source = """
package main

func caller() {
    obj.Method(42)
}
"""
        nodes, edges = parser.parse_file(Path("main.go"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert len(calls) >= 1
        assert calls[0].name == "Method"

    def test_parse_nested_call_in_arguments(self, parser: GoParser) -> None:
        """Chamada aninhada nos argumentos (outer(inner())) deve extrair ambas."""
        source = """
package main

func caller() {
    process(transform(fetch()))
}
"""
        nodes, edges = parser.parse_file(Path("main.go"), source)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert call_names == {"process", "transform", "fetch"}
