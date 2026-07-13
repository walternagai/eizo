.PHONY: dev install test lint typecheck clean coverage

# ─── Instalação ────────────────────────────────────────────────

install:
	pip install -e ".[dev]"

dev:
	pip install -e ".[dev]"

# ─── Testes ────────────────────────────────────────────────────

test:
	python3 -m pytest -v

test-quiet:
	python3 -m pytest -q --tb=short

coverage:
	python3 -m pytest --cov=src/eizo --cov-report=term-missing -v

# ─── Lint ──────────────────────────────────────────────────────

lint:
	python3 -m ruff check src/eizo/ tests/

lint-fix:
	python3 -m ruff check --fix src/eizo/ tests/

typecheck:
	python3 -m mypy src/eizo/

# ─── Limpeza ───────────────────────────────────────────────────

clean:
	rm -rf *.egg-info/ .pytest_cache/ __pycache__/
	rm -rf src/*.egg-info/ src/*/__pycache__/
	rm -rf tests/__pycache__/
	rm -rf .coverage coverage/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ─── Tudo ──────────────────────────────────────────────────────

check: lint typecheck test

all: clean install check
