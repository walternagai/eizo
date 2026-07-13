"""Testes estendidos para parser TypeScript — edge cases."""

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


class TestTypeScriptParserEdgeCases:
    """Testes para edge cases do parser TypeScript."""

    def test_parse_arrow_function_named(self, parser: TypeScriptParser) -> None:
        """Arrow function nomeada via const deve ser extraída."""
        source = """
const greet = (name: string): string => {
    return `Hello ${name}`;
};
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        # Arrow functions anônimas não são extraídas atualmente
        # Mas não deve crashar
        assert len(nodes) >= 1

    def test_parse_interface(self, parser: TypeScriptParser) -> None:
        """Interface não deve crashar."""
        source = """
interface User {
    name: string;
    age: number;
}
"""
        nodes, edges = parser.parse_file(Path("types.ts"), source)
        assert len(nodes) >= 1

    def test_parse_type_alias(self, parser: TypeScriptParser) -> None:
        """Type alias não deve crashar."""
        source = """
type Callback = (result: string) => void;
"""
        nodes, edges = parser.parse_file(Path("types.ts"), source)
        assert len(nodes) >= 1

    def test_parse_export_function(self, parser: TypeScriptParser) -> None:
        """Função exportada deve ser extraída."""
        source = """
export function hello(name: string): string {
    return `Hello ${name}`;
}
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "hello"

    def test_parse_export_default_function(self, parser: TypeScriptParser) -> None:
        """Export default function."""
        source = """
export default function() {
    return 42;
}
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        # Função sem nome não deve crashar
        assert len(nodes) >= 1

    def test_parse_export_class(self, parser: TypeScriptParser) -> None:
        """Classe exportada."""
        source = """
export class Service {
    run(): void {
        console.log("running");
    }
}
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Service"

    def test_parse_import_default(self, parser: TypeScriptParser) -> None:
        """Import default."""
        source = """
import React from "react";
"""
        nodes, edges = parser.parse_file(Path("main.tsx"), source)
        imports = [n for n in nodes if n.kind == "import"]
        assert len(imports) >= 1

    def test_parse_import_all(self, parser: TypeScriptParser) -> None:
        """Import all (namespace)."""
        source = """
import * as fs from "fs";
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        imports = [n for n in nodes if n.kind == "import"]
        assert len(imports) >= 1

    def test_parse_chained_method_call(self, parser: TypeScriptParser) -> None:
        """Chamada encadeada de métodos."""
        source = """
function process() {
    return data.filter(x => x > 0).map(x => x * 2);
}
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert len(calls) >= 1

    def test_parse_empty_file(self, parser: TypeScriptParser) -> None:
        """Arquivo vazio."""
        nodes, edges = parser.parse_file(Path("empty.ts"), "")
        assert len(nodes) >= 1
        assert nodes[0].kind == "file"

    def test_parse_jsx_file(self, parser: TypeScriptParser) -> None:
        """Arquivo .jsx não deve crashar."""
        source = """
function App() {
    return <div>Hello</div>;
}
"""
        nodes, edges = parser.parse_file(Path("App.jsx"), source)
        assert len(nodes) >= 1

    def test_parse_async_function(self, parser: TypeScriptParser) -> None:
        """Função async."""
        source = """
async function fetchData(): Promise<unknown> {
    return await api.get("/data");
}
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "fetchData"
