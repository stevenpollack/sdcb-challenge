VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

.PHONY: setup run serve-webapp test test-e2e coverage test-report lint

setup:
	python3 -m venv $(VENV)
	$(PIP) install -e ".[e2e]" pytest pytest-asyncio pytest-cov ruff
	$(VENV)/bin/playwright install chromium

run:
	$(PYTHON) -m matrixtui

serve-webapp:
	$(PYTHON) -c "from textual_serve.server import Server; Server('$(PYTHON) tests/e2e/mock_app.py', port=8765).serve()"

test:
	$(PYTEST) tests/ -v --tb=short

test-e2e:
	$(PYTEST) tests/e2e/ -v --tb=short

coverage:
	$(PYTEST) tests/ -m "not integration" --cov=matrixtui --cov-report=json:coverage-summary.json --tb=short
	$(PYTHON) -c "\
import json; \
raw = json.load(open('coverage-summary.json')); \
totals = raw.get('totals', {}); \
pct = totals.get('percent_covered', 0); \
summary = {'total': {'lines': {'pct': round(pct, 2)}}}; \
json.dump(summary, open('coverage-summary.json', 'w')); \
print(f'Coverage: {pct:.1f}%')"

test-report:
	$(PYTEST) tests/ -m "not integration" --junitxml=junit.xml --tb=short

lint:
	$(RUFF) check matrixtui/ tests/ || true
	@exit 0
