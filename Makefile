.PHONY: test lint typecheck check

test:
	uv run pytest

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy src

check: lint typecheck test
