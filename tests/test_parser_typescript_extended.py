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
        """Arrow function nomeada via const deve ser extraída como function."""
        source = """
const greet = (name: string): string => {
    return `Hello ${name}`;
};
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "greet"

    def test_parse_arrow_function_calls_body(self, parser: TypeScriptParser) -> None:
        """Chamadas dentro do corpo de uma arrow function devem ser extraídas."""
        source = """
const run = () => {
    doWork();
};
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert "doWork" in call_names
        # doWork deve ser atribuído ao escopo da função nomeada 'run'.
        run_node = next(n for n in nodes if n.kind == "function" and n.name == "run")
        assert any(
            e.kind == "calls" and e.source_id == run_node.id and e.metadata.get("call_name") == "doWork"
            for e in edges
        )

    def test_parse_arrow_function_anonymous_callback(self, parser: TypeScriptParser) -> None:
        """Callback inline anônimo (ex: useEffect) não vira function, mas suas
        chamadas internas ainda devem ser extraídas."""
        source = """
useEffect(() => {
    doSomething();
}, []);
"""
        nodes, edges = parser.parse_file(Path("main.tsx"), source)
        # A arrow function anônima em si não deve virar um nó function/method
        # (não há nome de variável nem propriedade para nomeá-la).
        assert not any(n.kind in ("function", "method") for n in nodes)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert {"useEffect", "doSomething"} <= call_names

    def test_parse_arrow_function_object_method(self, parser: TypeScriptParser) -> None:
        """Arrow function como propriedade de objeto deve virar method nomeado."""
        source = """
const service = {
    handler: () => { process(); }
};
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "handler"
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert "process" in call_names

    def test_parse_arrow_function_class_field(self, parser: TypeScriptParser) -> None:
        """Arrow function como class field (method = () => ...) vira method nomeado."""
        source = """
class Service {
    handler = () => { process(); };
}
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "handler"
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert "process" in call_names

    def test_parse_nested_call_in_arguments(self, parser: TypeScriptParser) -> None:
        """Chamada aninhada nos argumentos (outer(inner())) deve extrair ambas."""
        source = """
function caller() {
    process(transform(fetch()));
}
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert call_names == {"process", "transform", "fetch"}

    def test_parse_function_expression_named_via_const(self, parser: TypeScriptParser) -> None:
        """function expression atribuída a const (`const foo = function(){}`)
        deve ser extraída como function, com chamadas internas capturadas."""
        source = """
const foo = function() {
    bar();
};
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "foo"
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert "bar" in call_names

    def test_parse_function_expression_own_name(self, parser: TypeScriptParser) -> None:
        """function expression com nome próprio (`function namedFn(){}`)
        usa esse nome diretamente, mesmo sem atribuição a variável."""
        source = """
arr.forEach(function namedFn() {
    baz();
});
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "namedFn"
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert {"forEach", "baz"} <= call_names

    def test_parse_function_expression_anonymous_callback(self, parser: TypeScriptParser) -> None:
        """function expression anônima (callback inline) não vira nó nomeado,
        mas chamadas internas ainda são capturadas."""
        source = """
arr.forEach(function() {
    qux();
});
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        assert not any(n.kind in ("function", "method") for n in nodes)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert {"forEach", "qux"} <= call_names

    def test_parse_arrow_function_computed_key_stays_anonymous(
        self, parser: TypeScriptParser
    ) -> None:
        """Arrow function como valor de chave computada (`{ [expr]: () => {} }`)
        não deve virar um nó nomeado com o texto literal da expressão."""
        source = """
const key = "handler";
const obj = {
    [key]: () => { process(); }
};
"""
        nodes, edges = parser.parse_file(Path("main.ts"), source)
        assert not any(n.kind in ("function", "method") for n in nodes)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert "process" in call_names

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
