"""Testes para parser/python.py."""

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


class TestPythonParser:
    """Testes para o parser Python."""

    def test_language_property(self, parser: PythonParser) -> None:
        """Propriedade language deve retornar 'python'."""
        assert parser.language == "python"

    def test_extensions(self, parser: PythonParser) -> None:
        """Extensões devem incluir .py."""
        assert ".py" in parser.extensions

    def test_parse_empty_file(self, parser: PythonParser) -> None:
        """Arquivo vazio deve retornar apenas o nó do arquivo."""
        nodes, edges = parser.parse_file(Path("empty.py"), "")
        assert len(nodes) >= 1
        assert nodes[0].kind == "file"

    def test_parse_function(self, parser: PythonParser) -> None:
        """Deve extrair definições de função."""
        source = """
def hello(name: str) -> str:
    return f"Hello, {name}!"
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "hello"

    def test_parse_class(self, parser: PythonParser) -> None:
        """Deve extrair definições de classe."""
        source = """
class MyClass:
    def method(self) -> None:
        pass
"""
        nodes, edges = parser.parse_file(Path("model.py"), source)
        classes = [n for n in nodes if n.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "MyClass"

    def test_parse_class_with_inheritance(self, parser: PythonParser) -> None:
        """Deve extrair relação de herança."""
        source = """
class Base:
    pass

class Derived(Base):
    pass
"""
        nodes, edges = parser.parse_file(Path("model.py"), source)
        inherits = [e for e in edges if e.kind == "inherits"]
        assert len(inherits) >= 1

    def test_parse_imports(self, parser: PythonParser) -> None:
        """Deve extrair imports."""
        source = """
import os
from typing import Optional, List
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        imports = [n for n in nodes if n.kind == "import"]
        assert len(imports) >= 1

    def test_parse_calls(self, parser: PythonParser) -> None:
        """Deve extrair chamadas de função."""
        source = """
def caller() -> None:
    result = callee(42)
"""
        nodes, edges = parser.parse_file(Path("main.py"), source)
        calls = [n for n in nodes if n.kind == "call"]
        assert len(calls) >= 1

    def test_parse_sample_file(self, parser: PythonParser, sample_python_file: str) -> None:
        """Deve parsear arquivo de exemplo completo."""
        nodes, edges = parser.parse_file(Path("sample.py"), sample_python_file)

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

    def test_parse_docstring(self, parser: PythonParser) -> None:
        """Deve extrair docstrings de funções e classes."""
        source = '''
def documented() -> None:
    """Esta função tem docstring."""
    pass

class DocClass:
    """Classe com docstring."""
    pass
'''
        nodes, edges = parser.parse_file(Path("main.py"), source)
        funcs = [n for n in nodes if n.kind == "function"]
        classes = [n for n in nodes if n.kind == "class"]

        assert any(n.docstring == "Esta função tem docstring." for n in funcs)
        assert any(n.docstring == "Classe com docstring." for n in classes)
