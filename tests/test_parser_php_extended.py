"""Testes estendidos para parser PHP — regressão de node_id e edge cases."""

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


class TestPhpNodeIdDisambiguation:
    """Regressão: _node_id inclui coluna, e chamadas encadeadas ao mesmo
    método não colidem no mesmo id (mesma classe de defeito corrigida nos
    parsers Python, TypeScript, Go, Rust e Java)."""

    def test_same_name_same_line_distinct_columns_get_distinct_ids(self, parser: PhpParser) -> None:
        """Dois métodos HOMÔNIMOS em classes distintas na mesma linha física.

        Nomes diferentes já produzem hashes diferentes mesmo sem a coluna,
        por incluírem o nome — só o mesmo nome na mesma linha física expõe
        se a coluna está de fato no cálculo do id.
        """
        source = "<?php class A{function mul(){}}class B{function mul(){}}\n"
        nodes, _ = parser.parse_file(Path("Min.php"), source)
        muls = [n for n in nodes if n.name == "mul" and n.kind == "method"]
        assert len(muls) == 2
        assert muls[0].line_start == muls[1].line_start == 1
        assert muls[0].id != muls[1].id

    def test_chained_calls_to_same_method_get_distinct_ids(self, parser: PhpParser) -> None:
        """"$x->f()->f()" — duas chamadas a `f` na mesma linha, receivers diferentes.

        A posição correta é a do nó do nome do método dentro do
        member_call_expression (o identificador do método), não a do
        member_call inteiro (que para o segundo `->f()` da cadeia engloba a
        chamada anterior) — senão as duas chamadas a `f` colidiriam no
        mesmo id.
        """
        source = "<?php function run() {\n  $x->f()->f();\n}\n"
        nodes, _ = parser.parse_file(Path("Chain.php"), source)
        calls = [n for n in nodes if n.kind == "call" and n.name == "f"]
        assert len(calls) == 2
        assert calls[0].id != calls[1].id


class TestPhpParserEdgeCases:
    """Edge cases adicionais do parser PHP."""

    def test_class_without_name_does_not_crash(self, parser: PhpParser) -> None:
        """AST malformada (classe sem nome) não deve crashar o parser."""
        source = "<?php class { }\n"
        nodes, _ = parser.parse_file(Path("Bad.php"), source)
        assert len(nodes) >= 1  # pelo menos o file node

    def test_anonymous_class_does_not_crash(self, parser: PhpParser) -> None:
        """Classe anônima (`new class { ... }`) não deve crashar o parser."""
        source = "<?php $x = new class { public function m() {} };\n"
        nodes, _ = parser.parse_file(Path("Anon.php"), source)
        assert len(nodes) >= 1  # pelo menos o file node

    def test_multiple_classes_in_same_file(self, parser: PhpParser) -> None:
        """Múltiplas classes top-level no mesmo arquivo são extraídas."""
        source = """
<?php
class A {}
class B {}
"""
        nodes, _ = parser.parse_file(Path("Main.php"), source)
        classes = {n.name for n in nodes if n.kind == "class"}
        assert classes == {"A", "B"}

    def test_namespaced_class_name_is_preserved(self, parser: PhpParser) -> None:
        """Classe dentro de namespace mantém o nome simples (sem prefixo)."""
        source = """
<?php
namespace App\\Models;
class Dog {}
"""
        nodes, _ = parser.parse_file(Path("Dog.php"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "Dog"

    def test_qualified_base_name_is_preserved(self, parser: PhpParser) -> None:
        """`class X extends \\App\\Base` deve preservar o nome qualificado."""
        source = """
<?php
class Dog extends \\App\\Models\\Animal {
}
"""
        nodes, edges = parser.parse_file(Path("Dog.php"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].metadata.get("base_name") == "\\App\\Models\\Animal"

    def test_closure_does_not_become_function(self, parser: PhpParser) -> None:
        """Closure (`function () {}` anônima) NÃO deve virar 'function'."""
        source = """
<?php
$fn = function () { return 1; };
"""
        nodes, _ = parser.parse_file(Path("Main.php"), source)
        functions = [n for n in nodes if n.kind == "function"]
        assert len(functions) == 0

    def test_nullable_type_method_does_not_crash(self, parser: PhpParser) -> None:
        """Método com tipo nullable (`?Type`) não deve crashar o parser."""
        source = """
<?php
class Dog {
    public function find(?int $id): ?Dog {
        return null;
    }
}
"""
        nodes, _ = parser.parse_file(Path("Dog.php"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "find"
