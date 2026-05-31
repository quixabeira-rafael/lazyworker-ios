PYTHON ?= $(PWD)/.venv/bin/python

.PHONY: install uninstall dev test lint gate

# Install the CLI globally (isolated pipx venv, editable so dev changes apply).
install:
	pipx install -e . --python "$(PYTHON)" --force

uninstall:
	pipx uninstall lazyworker

# Local dev environment (tests + tooling) inside .venv.
dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m mypy src

gate: lint test
