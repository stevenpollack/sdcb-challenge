# Makefile for matrixtui — Matrix TUI client
# The harness calls these targets directly.

.PHONY: setup run test coverage test-report lint

setup:
	pip3 install --break-system-packages -e ".[dev]" 2>/dev/null || pip install -e ".[dev]"

run:
	python3 -m matrixtui

test:
	python3 -m pytest tests/ -v --tb=short

coverage:
	python3 -m pytest tests/ --cov=matrixtui --cov-report=json:coverage-summary.json --tb=short -q

test-report:
	python3 -m pytest tests/ --junit-xml=junit.xml -q

lint:
	@echo "No linter configured (no-op lint target)" && exit 0
