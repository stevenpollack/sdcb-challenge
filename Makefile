# Matrix TUI — Makefile
# All targets must exit 0 on success, non-zero on failure.

.PHONY: setup run test coverage test-report lint

setup:
	pip3 install -e ".[dev]" --break-system-packages --quiet 2>/dev/null || pip install -e ".[dev]" --quiet

PYTHON ?= $(shell command -v python3 || command -v python)

run:
	$(PYTHON) -m matrixclient.main

test:
	$(PYTHON) -m pytest tests/ -v -x

coverage:
	$(PYTHON) -m pytest tests/ --cov=matrixclient --cov-report=json:coverage-summary.json

test-report:
	$(PYTHON) -m pytest tests/ --junit-xml=junit.xml

lint:
	$(PYTHON) -m py_compile src/matrixclient/*.py && echo "Lint OK"
