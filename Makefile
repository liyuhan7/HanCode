.PHONY: test lint typecheck check

test:
	uv run pytest

lint:
	uv run ruff check src tests scripts

typecheck:
	uv run mypy src

check: lint typecheck test
