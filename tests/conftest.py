"""Fixtures compartilhadas para testes."""

from __future__ import annotations

from pathlib import Path

import pytest

from eizo.graph.store import GraphStore


@pytest.fixture
def store(tmp_path: Path) -> GraphStore:
    """GraphStore com banco em memória (via tmp_path)."""
    return GraphStore(tmp_path)


@pytest.fixture
def indexed_empty_repo(tmp_path: Path) -> Path:
    """Repositório já indexado porém sem símbolos.

    Diferente de um `tmp_path` cru: aqui `.eizo/graph.db` existe de fato, então
    os comandos de consulta o tratam como grafo vazio (saída normal, exit 0) em
    vez de repositório não indexado (erro, exit 1).
    """
    store = GraphStore(tmp_path)
    store.conn.execute("SELECT 1")  # força a criação do arquivo do banco
    store.close()
    return tmp_path


@pytest.fixture
def sample_python_file() -> str:
    """Código Python de exemplo para testes de parser."""
    return '''
from __future__ import annotations

import os
from typing import Optional


class Animal:
    """Classe base Animal."""

    def __init__(self, name: str) -> None:
        self.name = name

    def speak(self) -> str:
        """Faz o animal emitir som."""
        return f"{self.name} faz algum som"


class Dog(Animal):
    """Cachorro, herda de Animal."""

    def speak(self) -> str:
        return f"{self.name} late"


def create_animal(name: str, animal_type: str = "dog") -> Animal:
    """Factory function para criar animais."""
    if animal_type == "dog":
        return Dog(name)
    return Animal(name)


def main() -> None:
    """Função principal."""
    dog = create_animal("Rex")
    print(dog.speak())
'''


@pytest.fixture
def sample_ts_file() -> str:
    """Código TypeScript de exemplo para testes de parser."""
    return '''
import { Component } from "react";
import { render } from "react-dom";

interface Animal {
    name: string;
    speak(): string;
}

class Dog implements Animal {
    name: string;

    constructor(name: string) {
        this.name = name;
    }

    speak(): string {
        return `${this.name} barks`;
    }
}

function createAnimal(name: string, type: string = "dog"): Animal {
    if (type === "dog") {
        return new Dog(name);
    }
    return { name, speak: () => `${name} makes sound` };
}

function main(): void {
    const dog = createAnimal("Rex");
    console.log(dog.speak());
}
'''


@pytest.fixture
def sample_python_repo(tmp_path: Path) -> Path:
    """Cria um repositório Python de exemplo para testes de indexação."""
    repo = tmp_path / "python_repo"
    repo.mkdir()

    (repo / "main.py").write_text("""
from __future__ import annotations

from utils.helpers import greet, add


def main() -> None:
    name = "World"
    msg = greet(name)
    print(msg)
    result = add(1, 2)
    print(result)


if __name__ == "__main__":
    main()
""")

    utils_dir = repo / "utils"
    utils_dir.mkdir()
    (utils_dir / "__init__.py").write_text("")
    (utils_dir / "helpers.py").write_text(
        "from __future__ import annotations\n\n\n"
        'def greet(name: str) -> str:\n'
        '    """Sauda uma pessoa."""\n'
        '    return f"Hello, {name}!"\n\n\n'
        'def add(a: int, b: int) -> int:\n'
        '    """Soma dois números."""\n'
        "    return a + b\n"
    )

    return repo
