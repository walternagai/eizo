"""Fuzz tests dos parsers (B11 — Sprint #8 Robustez).

Alimenta os parsers com inputs malformados/aleatórios e garante que o parse
nunca levanta exceção. O gerador é determinístico (seed fixa) — sem
biblioteca hypothesis: random + seed fixa atende o requisito, mantém a suite
reproduzível e não adiciona dependência dev.
"""

from __future__ import annotations

import random
import string
from pathlib import Path

import pytest

from eizo.parser.base import BaseParser
from eizo.parser.csharp import CSharpParser
from eizo.parser.go import GoParser
from eizo.parser.java import JavaParser
from eizo.parser.php import PhpParser
from eizo.parser.python import PythonParser
from eizo.parser.ruby import RubyParser
from eizo.parser.rust import RustParser
from eizo.parser.typescript import TypeScriptParser

# Seed fixa: garante que a sequência de inputs aleatórios é idêntica a cada
# execução — o teste é 100% reproduzível e estável no CI.
FUZZ_SEED = 42
FUZZ_CASES = 50

# Arquivos sintéticos: os parsers só usam file_path para gerar ids e o nome do
# nó 'file' — paths inexistentes nunca são abertos.
FAKE_PATHS = {
    "csharp": Path("fuzz_input.cs"),
    "go": Path("fuzz_input.go"),
    "java": Path("fuzz_input.java"),
    "php": Path("fuzz_input.php"),
    "python": Path("fuzz_input.py"),
    "ruby": Path("fuzz_input.rb"),
    "rust": Path("fuzz_input.rs"),
    "typescript": Path("fuzz_input.ts"),
}

PARSERS: dict[str, type[BaseParser]] = {
    "csharp": CSharpParser,
    "python": PythonParser,
    "typescript": TypeScriptParser,
    "go": GoParser,
    "rust": RustParser,
    "java": JavaParser,
    "php": PhpParser,
    "ruby": RubyParser,
}

# Casos adicionais exercitam delimitadores e construções que cada gramática
# trata de forma diferente. Continuam sendo entradas deliberadamente
# incompletas: o parser deve devolver uma árvore parcial, não levantar exceção.
LANGUAGE_MALFORMED_CASES: dict[str, list[str]] = {
    "csharp": [
        "namespace Demo { class Broken { public void Run( { }",
        "using System; class C : { }",
    ],
    "php": [
        "<?php class Broken { public function run( { }",
        "<?php namespace Demo; function broken( {",
    ],
    "ruby": [
        "class Broken\n  def run(\n",
        "module Demo\n  def self.build\n",
    ],
}

# Casos malformados conhecidos (sintaxe quebrada deliberadamente) — o
# tree-sitter é tolerante a erro por design: produz árvore com nós ERROR em
# vez de levantar exceção, e os parsers só leem campos presentes.
MALFORMED_CASES: list[str] = [
    "",
    "(",
    ")",
    "{",
    "class {",
    "fn main( {",
    "def ():",
    "package main",
    "import x y z",
    "/*",
    "*/",
    '"""',
    "'",
    '"',
    "\\",
    "\x00",
    "\x00" * 100,
    "a" * 100000,
    "class",
    "fn",
    "func",
    "def",
    "interface",
    "impl",
    "use std::",
    "let x = ",
    "if (",
    "while (",
    "for (",
    "struct {",
    "enum {",
    "pub fn",
    "async fn",
    "impl<T>",
    "@",
    "#",
    "$",
    "// comment only",
    "# comment only",
    "/* comment only */",
    "-- comment only",
    "  \n\t  \n  ",
    "\n\n\n\n\n",
    "() => {}",
    "<T>",
    "T::new(",
    "obj.method(",
    "x.y.z(",
    "macro_rules!",
    "println!",
]


def _random_cases(rng: random.Random) -> list[str]:
    """Gera inputs aleatórios determinísticos.

    Combina bytes aleatórios (incluindo bytes inválidos UTF-8, decodificados
    com errors='replace' — exatamente como o indexer lê arquivos, ver
    indexer.py `read_text(encoding='utf-8', errors='replace')`) com pedaços
    de sintaxe real de cada linguagem (para exercitar caminhos do parser com
    árvores parcialmente válidas).
    """
    token_pool = [
        "fn", "func", "def", "class", "struct", "enum", "impl", "trait",
        "use", "import", "package", "mod", "let", "pub", "async", "fn main",
        "(", ")", "{", "}", "[", "]", ";", ",", "::", "->", "=>", "!",
        "&", "*", "|", "=", "+", "\"", "'", "\\", "\n", " ", "a", "b", "x",
        "self", "Self", "String", "int", "T", "true", "false", "None", "null",
        "@", "#", "$", "0", "1", "42", "0x", "0b",
    ]
    cases: list[str] = []
    for _ in range(FUZZ_CASES):
        n_tokens = rng.randint(1, 40)
        case = " ".join(rng.choice(token_pool) for _ in range(n_tokens))
        cases.append(case)

    # Bytes aleatórios crus (incluindo inválidos UTF-8), decodificados como
    # o indexer faz — o parser nunca deve ver um bytes cru.
    for _ in range(FUZZ_CASES):
        raw = bytes(rng.randint(0, 255) for _ in range(rng.randint(0, 500)))
        cases.append(raw.decode("utf-8", errors="replace"))

    # Strings com caracteres de controle/unicode variado.
    control = "".join(chr(rng.randint(0, 31)) for _ in range(rng.randint(1, 50)))
    cases.append(control)
    unicode = "".join(
        rng.choice(string.printable + "çãõéá日本語λ") for _ in range(rng.randint(1, 200))
    )
    cases.append(unicode)

    return cases


@pytest.mark.parametrize("language", sorted(PARSERS))
def test_parser_does_not_crash_on_malformed_input(language: str) -> None:
    """Nenhum input malformado/aleatório pode levantar exceção (B11)."""
    parser_cls = PARSERS[language]
    parser = parser_cls()
    rng = random.Random(FUZZ_SEED)
    inputs = MALFORMED_CASES + LANGUAGE_MALFORMED_CASES.get(language, []) + _random_cases(rng)
    for source in inputs:
        nodes, edges = parser.parse_file(FAKE_PATHS[language], source)
        assert isinstance(nodes, list)
        assert isinstance(edges, list)
        assert len(nodes) >= 1  # pelo menos o nó 'file'


@pytest.mark.parametrize("language", sorted(PARSERS))
def test_parser_fuzz_deterministic(language: str) -> None:
    """Mesma seed → mesma sequência de inputs (reproduzibilidade do fuzz)."""
    rng_a = random.Random(FUZZ_SEED)
    rng_b = random.Random(FUZZ_SEED)
    cases_a = _random_cases(rng_a)
    cases_b = _random_cases(rng_b)
    assert cases_a == cases_b
    # Os inputs são realmente não-vazios e variados — protege contra um
    # gerador degenerado que faça o teste passar por vacuidade.
    assert len(cases_a) >= FUZZ_CASES
    assert len(set(cases_a)) > FUZZ_CASES // 2
