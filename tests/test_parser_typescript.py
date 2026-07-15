"""Testes para parser/typescript.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.parser.typescript import TypeScriptParser


@pytest.fixture
def parser() -> TypeScriptParser:
    """Parser TypeScript para testes."""
    try:
        return TypeScriptParser()
    except RuntimeError:
        pytest.skip("tree-sitter-typescript não instalado")


class TestTypeScriptParser:
    """Testes para o parser TypeScript."""

    def test_language_property(self, parser: TypeScriptParser) -> None:
        """Propriedade language deve retornar 'typescript'."""
        assert parser.language == "typescript"

    def test_extensions(self, parser: TypeScriptParser) -> None:
        """Extensões devem incluir .ts, .tsx, .js, .jsx."""
        assert ".ts" in parser.extensions
        assert ".tsx" in parser.extensions
        assert ".js" in parser.extensions
        assert ".jsx" in parser.extensions

    def test_parse_empty_file(self, parser: TypeScriptParser) -> None:
        """Arquivo vazio deve retornar apenas o nó do arquivo."""
        nodes, edges = parser.parse_file(Path("empty.ts"), "")
        assert len(nodes) >= 1
        assert nodes[0].kind == "file"

    def test_parse_function(self, parser: TypeScriptParser) -> None:
        """Deve extrair declarações de função."""
        source = """
function hello(name: string): string {
    return `Hello, ${name}!`;
}
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "hello"

    def test_parse_class(self, parser: TypeScriptParser) -> None:
        """Deve extrair declarações de classe."""
        source = """
class MyClass {
    method(): void {
        console.log("hello");
    }
}
"""
        nodes, edges = parser.parse_file(Path("model.ts"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "MyClass"

    def test_parse_class_with_extends(self, parser: TypeScriptParser) -> None:
        """Deve extrair relação de herança."""
        source = """
class Base {
    baseMethod(): void {}
}

class Derived extends Base {
    derivedMethod(): void {}
}
"""
        nodes, edges = parser.parse_file(Path("model.ts"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) >= 1

    def test_parse_imports(self, parser: TypeScriptParser) -> None:
        """Deve extrair imports."""
        source = """
import { Component } from "react";
import fs from "fs";
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        imports = [n for n in nodes if n.kind == "import"]
        assert len(imports) >= 1

    def test_parse_calls(self, parser: TypeScriptParser) -> None:
        """Deve extrair chamadas de função."""
        source = """
function caller(): void {
    const result = callee(42);
}
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert len(calls) >= 1

    def test_parse_sample_file(self, parser: TypeScriptParser, sample_ts_file: str) -> None:
        """Deve parsear arquivo de exemplo completo."""
        nodes, edges = parser.parse_file(Path("sample.ts"), sample_ts_file)

        funcs = [n for n in nodes if n.kind == "function"]
        classes = [n for n in nodes if n.kind == "class"]
        methods = [n for n in nodes if n.kind == "method"]
        imports = [n for n in nodes if n.kind == "import"]

        assert len(funcs) >= 1
        assert len(classes) >= 1
        assert len(methods) >= 1
        assert len(imports) >= 1

        # Verifica contains edges
        contains = [e for e in edges if e.kind == "contains"]
        assert len(contains) >= 1
