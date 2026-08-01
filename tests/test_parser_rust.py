"""Testes para parser/rust.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.parser.rust import RustParser


@pytest.fixture
def parser() -> RustParser:
    """Parser Rust para testes."""
    try:
        return RustParser()
    except RuntimeError:
        pytest.skip("tree-sitter-rust não instalado")


class TestRustParser:
    """Testes para o parser Rust."""

    def test_language_property(self, parser: RustParser) -> None:
        """Propriedade language deve retornar 'rust'."""
        assert parser.language == "rust"

    def test_extensions(self, parser: RustParser) -> None:
        """Extensões devem incluir .rs."""
        assert ".rs" in parser.extensions

    def test_parse_empty_file(self, parser: RustParser) -> None:
        """Arquivo vazio deve retornar apenas o nó do arquivo."""
        nodes, edges = parser.parse_file(Path("empty.rs"), "")
        assert len(nodes) >= 1
        assert nodes[0].kind == "file"

    def test_parse_function(self, parser: RustParser) -> None:
        """Deve extrair funções top-level."""
        source = """
fn hello(name: &str) -> String {
    format!("Hello, {}", name)
}
"""
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "hello"

    def test_parse_struct_as_class(self, parser: RustParser) -> None:
        """Struct deve ser extraído como 'class'."""
        source = """
struct Dog {
    name: String,
}
"""
        nodes, edges = parser.parse_file(Path("model.rs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Dog"

    def test_parse_trait_as_class(self, parser: RustParser) -> None:
        """Trait deve ser extraído como 'class'."""
        source = """
trait Animal {
    fn speak(&self) -> String;
}
"""
        nodes, edges = parser.parse_file(Path("model.rs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Animal"

    def test_parse_enum_as_class(self, parser: RustParser) -> None:
        """Enum deve ser extraído como 'class'."""
        source = """
enum Status {
    Ok,
    Err(String),
}
"""
        nodes, edges = parser.parse_file(Path("model.rs"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Status"

    def test_parse_method_via_impl(self, parser: RustParser) -> None:
        """Método dentro de `impl Tipo {...}` deve virar 'method' com 'contains' do struct."""
        source = """
struct Dog {
    name: String,
}

impl Dog {
    fn speak(&self) -> String {
        self.name.clone()
    }
}
"""
        nodes, edges = parser.parse_file(Path("model.rs"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "speak"

        dog = next(n for n in nodes if n.kind == "class" and n.name == "Dog")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == methods[0].id]
        assert len(contains) == 1
        assert contains[0].source_id == dog.id

    def test_impl_declared_before_struct_still_resolves(self, parser: RustParser) -> None:
        """A ordem entre `impl Tipo {...}` e `struct Tipo {...}` no arquivo não importa."""
        source = """
impl Dog {
    fn speak(&self) -> String {
        self.name.clone()
    }
}

struct Dog {
    name: String,
}
"""
        nodes, edges = parser.parse_file(Path("model.rs"), source)
        method = next(n for n in nodes if n.kind == "method" and n.name == "speak")
        dog = next(n for n in nodes if n.kind == "class" and n.name == "Dog")
        contains = [e for e in edges if e.kind == "contains" and e.target_id == method.id]
        assert len(contains) == 1
        assert contains[0].source_id == dog.id

    def test_impl_trait_for_type_creates_inherits_edge(self, parser: RustParser) -> None:
        """`impl Trait for Tipo` vira aresta 'inherits' de Tipo para Trait."""
        source = """
trait Animal {
    fn speak(&self) -> String;
}

struct Dog {
    name: String,
}

impl Animal for Dog {
    fn speak(&self) -> String {
        self.name.clone()
    }
}
"""
        nodes, edges = parser.parse_file(Path("model.rs"), source)
        dog = next(n for n in nodes if n.kind == "class" and n.name == "Dog")
        animal = next(n for n in nodes if n.kind == "class" and n.name == "Animal")
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].source_id == dog.id
        assert inherits[0].target_id == animal.id
        assert inherits[0].metadata.get("base_name") == "Animal"

    def test_impl_trait_from_another_crate_creates_external_stub(self, parser: RustParser) -> None:
        """`impl Trait for Tipo` com trait não declarado neste arquivo cria stub externo."""
        source = """
struct Dog {
    name: String,
}

impl std::fmt::Display for Dog {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        Ok(())
    }
}
"""
        nodes, edges = parser.parse_file(Path("model.rs"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        external = next(n for n in nodes if n.id == inherits[0].target_id)
        assert external.metadata.get("external") is True

    def test_parse_simple_import(self, parser: RustParser) -> None:
        """`use std::fmt;` simples."""
        source = "use std::fmt;\n"
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"std::fmt"}

    def test_parse_import_with_alias(self, parser: RustParser) -> None:
        """`use X as Y`: resolve pelo nome real, não pelo alias local."""
        source = "use std::collections::HashMap as Map;\n"
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"std::collections::HashMap"}

    def test_parse_grouped_import(self, parser: RustParser) -> None:
        """`use std::{io, fs::File};` deve extrair ambos os caminhos completos."""
        source = "use std::{io, fs::File};\n"
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"std::io", "std::fs::File"}

    def test_parse_wildcard_import(self, parser: RustParser) -> None:
        """`use std::io::*;` deve extrair o caminho com sufixo '::*'."""
        source = "use std::io::*;\n"
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        import_names = {n.name for n in nodes if n.kind == "import"}
        assert import_names == {"std::io::*"}

    def test_parse_plain_call(self, parser: RustParser) -> None:
        """Deve extrair chamada de função simples."""
        source = """
fn caller() {
    callee(42);
}
"""
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert len(calls) >= 1
        assert calls[0].name == "callee"

    def test_parse_method_call(self, parser: RustParser) -> None:
        """Chamada de método (obj.metodo()) deve extrair o nome do método."""
        source = """
fn caller(obj: Dog) {
    obj.speak();
}
"""
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert len(calls) >= 1
        assert calls[0].name == "speak"

    def test_parse_associated_function_call(self, parser: RustParser) -> None:
        """Chamada de função associada (Tipo::funcao()) deve extrair o nome."""
        source = """
fn caller() {
    Dog::new();
}
"""
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert len(calls) >= 1
        assert calls[0].name == "new"

    def test_parse_nested_call_in_arguments(self, parser: RustParser) -> None:
        """Chamada aninhada nos argumentos (outer(inner())) deve extrair ambas."""
        source = """
fn caller() {
    process(transform(fetch()));
}
"""
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert call_names == {"process", "transform", "fetch"}

    def test_function_inside_mod_is_still_extracted(self, parser: RustParser) -> None:
        """Função dentro de `mod` deve continuar sendo extraída (recursão genérica)."""
        source = """
mod utils {
    pub fn helper() {}
}
"""
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "helper"
