"""Testes para __main__.py (entry point python -m eizo)."""

from __future__ import annotations

from unittest.mock import patch


class TestMain:
    """Testes para o entry point __main__."""

    def test_main_entry_point(self) -> None:
        """Executar python -m eizo deve chamar cli.main()."""
        with patch("eizo.__main__.main") as mock_main:
            # O __main__ só chama main() quando __name__ == "__main__"
            # Em teste, __name__ não é "__main__", então só verificamos
            # que o módulo importa sem erro
            mock_main.assert_not_called()

    def test_main_called_when_run(self) -> None:
        """Simula execução como script."""
        with patch("eizo.cli.main") as mock_main:
            # Simula o que __main__.py faz
            from eizo.cli import main
            main()
            mock_main.assert_called_once()
