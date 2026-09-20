"""Parser base abstrato para parsers de linguagem."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from eizo.graph.models import Edge, Node

# Profundidade máxima da travessia da AST — fonte única para os guardas de
# recursão dos 8 parsers (ver _walk_tree de cada um). Ordens de magnitude
# acima de qualquer código real; existe porque input legítimo pode ser
# aninhado mais fundo do que o limite de recursão do Python (bundles
# minificados com JSON/arrays de milhares de níveis).
MAX_AST_DEPTH = 500


class BaseParser(ABC):
    """Classe base para parsers de linguagem via Tree-sitter."""

    @property
    @abstractmethod
    def language(self) -> str:
        """Nome da linguagem (ex: 'python', 'typescript')."""
        ...

    @property
    @abstractmethod
    def extensions(self) -> set[str]:
        """Extensões de arquivo suportadas (ex: {'.py'})."""
        ...

    @abstractmethod
    def parse_file(self, file_path: Path, source: str) -> tuple[list[Node], list[Edge]]:
        """Parseia um arquivo e retorna nós e arestas.

        Args:
            file_path: Caminho do arquivo (para referência).
            source: Conteúdo do arquivo como string.

        Returns:
            Tupla (nodes, edges) representando símbolos e relações.
        """
        ...

    def should_parse(self, file_path: Path) -> bool:
        """Verifica se o arquivo deve ser parseado."""
        return file_path.suffix in self.extensions
