.PHONY: check format format-check lint test

check: lint format-check test

format:
	uv run ruff format .
	uv run ruff check --fix .

format-check:
	uv run ruff format --check .

lint:
	uv run ruff check .
	uv run mypy
	uv run python tools/static_checks.py

test:
	uv run pytest
