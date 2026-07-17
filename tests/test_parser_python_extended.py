"""Testes estendidos para parser Python — edge cases, decorators, type aliases."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.parser.python import PythonParser


@pytest.fixture
def parser() -> PythonParser:
    """Parser Python para testes."""
    try:
        return PythonParser()
    except RuntimeError:
        pytest.skip("tree-sitter-python não instalado")


class TestPythonParserEdgeCases:
    """Testes para edge cases do parser Python."""

    def test_parse_decorated_function(self, parser: PythonParser) -> None:
        """Função com decorator deve ser extraída."""
        source = """
from flask import route

@route("/api")
def hello() -> str:
    return "hello"
"""
        nodes, edges = parser.parse_file(Path("app.py"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "hello"

    def test_parse_nested_function(self, parser: PythonParser) -> None:
        """Função aninhada deve ser extraída como method (contida)."""
        source = """
def outer() -> None:
    def inner() -> None:
        pass
    inner()
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        funcs = [n for n in nodes if n.kind in ("function", "method")]
        assert len(funcs) >= 2
        contains = [e for e in edges if e.kind == "contains"]
        assert len(contains) >= 1

    def test_parse_lambda_not_extracted(self, parser: PythonParser) -> None:
        """Lambdas não devem ser extraídos como nós."""
        source = """
add = lambda x, y: x + y
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        # Lambda não é function_definition, não deve aparecer
        assert len(funcs) == 0

    def test_parse_class_without_name(self, parser: PythonParser) -> None:
        """Classe sem nome (malformada) não deve crashar."""
        source = """
class():
    pass
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        # Não deve crashar, apenas ignorar
        assert len(nodes) >= 1  # pelo menos o file node

    def test_parse_function_without_name(self, parser: PythonParser) -> None:
        """Função sem nome (malformada) não deve crashar."""
        source = """
def():
    pass
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        assert len(nodes) >= 1

    def test_parse_import_from_with_alias(self, parser: PythonParser) -> None:
        """Import from com alias."""
        source = """
from os import path as osp
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        imports = [n for n in nodes if n.kind == "import"]
        assert len(imports) >= 1

    def test_parse_multiple_imports(self, parser: PythonParser) -> None:
        """Múltiplos imports."""
        source = """
import os, sys, json
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        imports = [n for n in nodes if n.kind == "import"]
        assert len(imports) >= 1

    def test_parse_method_call(self, parser: PythonParser) -> None:
        """Chamada de método (obj.method()) deve extrair o nome do método."""
        source = """
def caller() -> None:
    obj.method(42)
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert len(calls) >= 1
        assert calls[0].name == "method"

    def test_parse_nested_call_in_arguments(self, parser: PythonParser) -> None:
        """Chamada aninhada nos argumentos (outer(inner())) deve extrair ambas."""
        source = """
def caller() -> None:
    process(transform(fetch()))
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        call_names = {n.name for n in nodes if n.kind == "call"}
        assert call_names == {"process", "transform", "fetch"}
        call_edges = {e.metadata.get("call_name") for e in edges if e.kind == "calls"}
        # Todas as chamadas aninhadas devem ser atribuídas ao mesmo escopo chamador.
        assert call_edges == {"process", "transform", "fetch"}

    def test_parse_async_function(self, parser: PythonParser) -> None:
        """Função async deve ser extraída."""
        source = """
async def fetch_data() -> dict:
    return {"ok": True}
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "fetch_data"

    def test_parse_class_with_methods(self, parser: PythonParser) -> None:
        """Classe com métodos deve extrair métodos como 'method' kind."""
        source = """
class Service:
    def do_work(self) -> None:
        pass

    def cleanup(self) -> None:
        pass
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        methods = [n for n in nodes if n.kind == "method"]
        assert len(methods) >= 2

    def test_parse_docstring_single_quotes(self, parser: PythonParser) -> None:
        """Docstring com aspas simples."""
        source = """
def simple() -> None:
    'Single line docstring'
    pass
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert any(n.docstring == "Single line docstring" for n in funcs)

    def test_parse_docstring_double_quotes(self, parser: PythonParser) -> None:
        """Docstring com aspas duplas."""
        source = '''
def simple() -> None:
    "Double line docstring"
    pass
'''
        nodes, edges = parser.parse_file(Path("main.py"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert any(n.docstring == "Double line docstring" for n in funcs)

    def test_parse_empty_body_function(self, parser: PythonParser) -> None:
        """Função com corpo vazio (ellipsis)."""
        source = """
def empty() -> None: ...
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "empty"
