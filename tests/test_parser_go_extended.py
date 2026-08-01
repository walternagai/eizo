"""Testes estendidos para parser Go — regressão de node_id e edge cases."""

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


class TestGoNodeIdDisambiguation:
    """Regressão: _node_id inclui coluna, e chamadas encadeadas ao mesmo
    método não colidem no mesmo id (mesma classe de defeito corrigida nos
    parsers Python e TypeScript)."""

    def test_same_name_same_line_distinct_columns_get_distinct_ids(self, parser: GoParser) -> None:
        """Duas funções HOMÔNIMAS na mesma linha física.

        Nomes diferentes já produzem hashes diferentes mesmo sem a coluna,
        por incluírem o nome — só o mesmo nome na mesma linha física expõe
        se a coluna está de fato no cálculo do id.
        """
        source = "package main\nfunc mul(){};func mul(){};\n"
        nodes, _ = parser.parse_file(Path("min.go"), source)
        muls = [n for n in nodes if n.name == "mul" and n.kind == "function"]
        assert len(muls) == 2
        assert muls[0].line_start == muls[1].line_start == 2
        assert muls[0].id != muls[1].id

    def test_chained_calls_to_same_method_get_distinct_ids(self, parser: GoParser) -> None:
        """"x.f().f()" — duas chamadas a `f` na mesma linha, operandos diferentes.

        A posição correta é a do "field" do selector_expression (o
        identificador do método), não a do selector_expression inteiro
        (que começa no operando `x`) — senão as duas chamadas a `f`
        colidiriam no mesmo id.
        """
        source = "package main\nfunc run() {\n  x.f().f()\n}\n"
        nodes, _ = parser.parse_file(Path("chain.go"), source)
        calls = [n for n in nodes if n.kind == "call" and n.name == "f"]
        assert len(calls) == 2
        assert calls[0].id != calls[1].id


class TestGoParserEdgeCases:
    """Edge cases adicionais do parser Go."""

    def test_parse_function_without_name(self, parser: GoParser) -> None:
        """Função malformada (sem nome) não deve crashar."""
        source = "package main\nfunc () {}\n"
        nodes, _ = parser.parse_file(Path("main.go"), source)
        assert len(nodes) >= 1  # pelo menos o file node

    def test_pointer_receiver_and_value_receiver_both_resolve(self, parser: GoParser) -> None:
        """Receiver por ponteiro (*T) e por valor (T) resolvem ao mesmo struct."""
        source = """
package main

type Dog struct {
    Name string
}

func (d *Dog) Speak() string {
    return d.Name
}

func (d Dog) Bark() string {
    return "Woof"
}
"""
        nodes, edges = parser.parse_file(Path("model.go"), source)
        dog = next(n for n in nodes if n.kind == "class" and n.name == "Dog")
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 2
        for method in methods:
            contains = [e for e in edges if e.kind == "contains" and e.target_id == method.id]
            assert len(contains) == 1
            assert contains[0].source_id == dog.id

    def test_method_with_unknown_receiver_type_has_no_contains_edge(self, parser: GoParser) -> None:
        """Receiver de um tipo não declarado neste arquivo: sem 'contains' (sem crash)."""
        source = """
package main

func (e ExternalType) Method() {}
"""
        nodes, edges = parser.parse_file(Path("main.go"), source)
        method = next(n for n in nodes if n.kind == "method")
        assert not any(e.kind == "contains" and e.target_id == method.id for e in edges)

    def test_parse_multiple_structs_and_interfaces(self, parser: GoParser) -> None:
        """Múltiplos structs/interfaces no mesmo arquivo."""
        source = """
package main

type A struct{}
type B interface{}
type C struct{}
"""
        nodes, _ = parser.parse_file(Path("main.go"), source)
        classes = {n.name for n in nodes if n.kind == "class"}
        assert classes == {"A", "B", "C"}

    def test_parse_variadic_and_multiple_returns_does_not_crash(self, parser: GoParser) -> None:
        """Assinaturas Go-específicas (variádicos, múltiplos retornos) não crasham."""
        source = """
package main

func sum(nums ...int) (int, error) {
    return 0, nil
}
"""
        nodes, _ = parser.parse_file(Path("main.go"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "sum"
