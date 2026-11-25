.PHONY: install run lint format typecheck test security check

# Install the package and all dev dependencies in editable mode.
install:
	pip install -e ".[dev]"

# Start the development server via the app factory with auto-reload.
run:
	uvicorn smogguide.main:create_app --factory --reload --host 0.0.0.0 --port 8000

# Check formatting and linting without modifying files.
lint:
	ruff check src tests
	ruff format --check src tests

# Apply auto-fixable formatting and lint fixes in-place.
format:
	ruff format src tests
	ruff check --fix src tests

# Run static type checking with mypy strict mode.
typecheck:
	mypy

# Run the full test suite with coverage.
test:
	pytest

# Run security scanner and dependency audit.
security:
	bandit -r src
	pip-audit

# Full quality gate: lint, typecheck, then test.
check: lint typecheck test
