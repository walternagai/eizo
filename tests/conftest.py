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
