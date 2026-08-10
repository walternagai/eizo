"""Testes para parser/php.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.parser.php import PhpParser


@pytest.fixture
def parser() -> PhpParser:
    """Parser PHP para testes."""
    try:
        return PhpParser()
    except RuntimeError:
        pytest.skip("tree-sitter-php não instalado")


class TestPhpParser:
    """Testes para o parser PHP."""

    def test_language_property(self, parser: PhpParser) -> None:
        """Propriedade language deve retornar 'php'."""
        assert parser.language == "php"

    def test_extensions(self, parser: PhpParser) -> None:
        """Extensões devem incluir .php."""
        assert ".php" in parser.extensions

    def test_parse_empty_file(self, parser: PhpParser) -> None:
        """Arquivo vazio deve retornar apenas o nó do arquivo."""
        nodes, edges = parser.parse_file(Path("Empty.php"), "")
        assert len(nodes) >= 1
        assert nodes[0].kind == "file"

    def test_parse_class(self, parser: PhpParser) -> None:
        """Deve extrair definições de classe."""
        source = """
<?php
class Dog {
    public function bark() {}
}
"""
        nodes, edges = parser.parse_file(Path("Dog.php"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Dog"

    def test_parse_interface_as_class(self, parser: PhpParser) -> None:
        """Interface deve ser extraída como 'class'."""
        source = """
<?php
interface IAnimal {
    public function speak();
}
"""
        nodes, edges = parser.parse_file(Path("IAnimal.php"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "IAnimal"

    def test_parse_trait_as_class(self, parser: PhpParser) -> None:
        """Trait deve ser extraído como 'class'."""
        source = """
<?php
trait Helper {
    public function help() {}
}
"""
        nodes, edges = parser.parse_file(Path("Helper.php"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Helper"

    def test_parse_enum_as_class(self, parser: PhpParser) -> None:
        """Enum (PHP 8.1+) deve ser extraído como 'class'."""
        source = """
<?php
enum Status {
    case Ok;
    case Err;
}
"""
        nodes, edges = parser.parse_file(Path("Status.php"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Status"

    def test_parse_method_attached_to_class(self, parser: PhpParser) -> None:
        """Método deve virar 'method' com 'contains' a partir da classe."""
        source = """
<?php
class Dog {
    public function bark() {}
}
"""
        nodes, edges = parser.parse_file(Path("Dog.php"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "bark"

        dog = next(n for n in nodes if n.kind == "class")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == methods[0].id]
        assert len(contains) == 1
        assert contains[0].source_id == dog.id

    def test_interface_abstract_method_has_no_body_but_is_extracted(self, parser: PhpParser) -> None:
        """Método abstrato de interface (sem corpo) ainda vira 'method'."""
        source = """
<?php
interface IAnimal {
    public function speak();
}
"""
        nodes, edges = parser.parse_file(Path("IAnimal.php"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "speak"

    def test_parse_top_level_function(self, parser: PhpParser) -> None:
        """Função top-level deve virar 'function'."""
        source = """
<?php
function top_level() {
    return 1;
}
"""
        nodes, edges = parser.parse_file(Path("lib.php"), source)
        functions = [n for n in nodes if n.kind == "function"]
        assert len(functions) == 1
        assert functions[0].name == "top_level"

    def test_parse_extends_creates_inherits_edge(self, parser: PhpParser) -> None:
        """`class X extends Y` deve criar aresta 'inherits'."""
        source = """
<?php
class Dog extends Animal {
}
"""
        nodes, edges = parser.parse_file(Path("Dog.php"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].metadata.get("base_name") == "Animal"

    def test_parse_implements_creates_inherits_edge(self, parser: PhpParser) -> None:
        """`class X implements A` deve criar aresta 'inherits'."""
        source = """
<?php
class Dog implements IComparable {
}
"""
        nodes, edges = parser.parse_file(Path("Dog.php"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].metadata.get("base_name") == "IComparable"

    def test_parse_extends_and_implements_together(self, parser: PhpParser) -> None:
        """`class X extends Y implements A` deve criar arestas para ambos."""
        source = """
<?php
class Dog extends Animal implements IComparable {
}
"""
        nodes, edges = parser.parse_file(Path("Dog.php"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        base_names = {e.metadata.get("base_name") for e in inherits}
        assert base_names == {"Animal", "IComparable"}

    def test_parse_use_import(self, parser: PhpParser) -> None:
        """`use App\\Models\\Dog;` deve virar import."""
        source = "<?php\nuse App\\Models\\Dog;\n"
        nodes, edges = parser.parse_file(Path("Main.php"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"App\\Models\\Dog"}

    def test_parse_use_function_import(self, parser: PhpParser) -> None:
        """`use function App\\helpers\\foo;` deve virar import."""
        source = "<?php\nuse function App\\helpers\\foo;\n"
        nodes, edges = parser.parse_file(Path("Main.php"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"App\\helpers\\foo"}

    def test_parse_plain_call(self, parser: PhpParser) -> None:
        """Deve extrair chamada de função sem receiver explícito."""
        source = """
<?php
function caller() {
    foo();
}
"""
        nodes, edges = parser.parse_file(Path("Main.php"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "foo" for c in calls)

    def test_parse_method_call_with_receiver(self, parser: PhpParser) -> None:
        """Chamada de método ($obj->metodo()) deve extrair o nome do método."""
        source = """
<?php
function caller($obj) {
    $obj->speak();
}
"""
        nodes, edges = parser.parse_file(Path("Main.php"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "speak" for c in calls)

    def test_parse_object_creation_as_call(self, parser: PhpParser) -> None:
        """`new Tipo()` deve virar uma chamada ao nome do tipo."""
        source = """
<?php
function caller() {
    $d = new Dog();
}
"""
        nodes, edges = parser.parse_file(Path("Main.php"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert any(c.name == "Dog" for c in calls)

    def test_parse_nested_call_in_arguments(self, parser: PhpParser) -> None:
        """Chamada aninhada nos argumentos (outer(inner())) deve extrair ambas."""
        source = """
<?php
function caller() {
    process(transform(fetch()));
}
"""
        nodes, edges = parser.parse_file(Path("Main.php"), source)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert call_names == {"process", "transform", "fetch"}
