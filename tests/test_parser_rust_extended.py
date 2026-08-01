"""Testes estendidos para parser Rust — regressão de node_id e edge cases."""

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


class TestRustNodeIdDisambiguation:
    """Regressão: _node_id inclui coluna, e chamadas encadeadas ao mesmo
    método não colidem no mesmo id (mesma classe de defeito corrigida nos
    parsers Python, TypeScript e Go)."""

    def test_same_name_same_line_distinct_columns_get_distinct_ids(self, parser: RustParser) -> None:
        """Duas funções HOMÔNIMAS na mesma linha física.

        Nomes diferentes já produzem hashes diferentes mesmo sem a coluna,
        por incluírem o nome — só o mesmo nome na mesma linha física expõe
        se a coluna está de fato no cálculo do id.
        """
        source = "fn mul(){};fn mul(){};\n"
        nodes, _ = parser.parse_file(Path("min.rs"), source)
        muls = [n for n in nodes if n.name == "mul" and n.kind == "function"]
        assert len(muls) == 2
        assert muls[0].line_start == muls[1].line_start == 1
        assert muls[0].id != muls[1].id

    def test_chained_calls_to_same_method_get_distinct_ids(self, parser: RustParser) -> None:
        """"x.f().f()" — duas chamadas a `f` na mesma linha, operandos diferentes.

        A posição correta é a do campo "field" do field_expression (o
        identificador do método), não a do field_expression inteiro (que
        começa no operando `x`) — senão as duas chamadas a `f` colidiriam
        no mesmo id.
        """
        source = "fn run() {\n  x.f().f();\n}\n"
        nodes, _ = parser.parse_file(Path("chain.rs"), source)
        calls = [n for n in nodes if n.kind == "call" and n.name == "f"]
        assert len(calls) == 2
        assert calls[0].id != calls[1].id


class TestRustParserEdgeCases:
    """Edge cases adicionais do parser Rust."""

    def test_multiple_impl_blocks_for_same_type_both_attach(self, parser: RustParser) -> None:
        """Dois blocos `impl` distintos para o mesmo tipo (inherent + trait) ambos ligam ao struct."""
        source = """
trait Animal {
    fn speak(&self) -> String;
}

struct Dog {
    name: String,
}

impl Dog {
    fn new() -> Self {
        Dog { name: String::new() }
    }
}

impl Animal for Dog {
    fn speak(&self) -> String {
        self.name.clone()
    }
}
"""
        nodes, edges = parser.parse_file(Path("model.rs"), source)
        dog = next(n for n in nodes if n.kind == "class" and n.name == "Dog")
        methods = [n for n in nodes if n.kind == "method"]
        assert {m.name for m in methods} == {"new", "speak"}
        for method in methods:
            contains = [e for e in edges if e.kind == "contains" and e.target_id == method.id]
            assert len(contains) == 1
            assert contains[0].source_id == dog.id

    def test_method_in_impl_for_unknown_type_has_no_contains_edge(self, parser: RustParser) -> None:
        """Impl para um tipo não declarado neste arquivo: sem 'contains' (sem crash)."""
        source = """
impl ExternalType {
    fn method(&self) {}
}
"""
        nodes, edges = parser.parse_file(Path("main.rs"), source)
        method = next(n for n in nodes if n.kind == "method")
        assert not any(e.kind == "contains" and e.target_id == method.id for e in edges)

    def test_function_without_name_does_not_crash(self, parser: RustParser) -> None:
        """AST malformada não deve crashar o parser."""
        source = "fn () {}\n"
        nodes, _ = parser.parse_file(Path("main.rs"), source)
        assert len(nodes) >= 1  # pelo menos o file node

    def test_parse_multiple_structs_traits_enums(self, parser: RustParser) -> None:
        """Múltiplos structs/traits/enums no mesmo arquivo."""
        source = """
struct A;
trait B {}
enum C { X, Y }
"""
        nodes, _ = parser.parse_file(Path("main.rs"), source)
        classes = {n.name for n in nodes if n.kind == "class"}
        assert classes == {"A", "B", "C"}

    def test_call_inside_macro_invocation_is_not_captured(self, parser: RustParser) -> None:
        """Limitação conhecida: chamadas dentro de macros (`println!`, `format!`,
        etc.) não são capturadas.

        tree-sitter-rust não parseia o argumento de uma macro como expressão —
        vira um `token_tree` de tokens crus (macros podem ter regras de
        expansão arbitrárias, então a gramática não tenta interpretá-las).
        `d.speak()` dentro de `println!(...)` nunca vira um `call_expression`.
        """
        source = """
fn main() {
    let d = 1;
    println!("{}", d.speak());
}
"""
        nodes, _ = parser.parse_file(Path("main.rs"), source)
        calls = {n.name for n in nodes if n.kind == "call"}
        assert "speak" not in calls

    def test_generic_function_signature_does_not_crash(self, parser: RustParser) -> None:
        """Assinaturas genéricas (`<T>`, `where`) não devem crashar o parser."""
        source = """
fn identity<T>(value: T) -> T where T: Clone {
    value.clone()
}
"""
        nodes, _ = parser.parse_file(Path("main.rs"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "identity"
