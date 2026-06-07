# matrixtui — Matrix Terminal UI Client

A terminal UI (TUI) client for the [Matrix](https://matrix.org) protocol, built with
[matrix-nio](https://github.com/poljar/matrix-nio) and [Textual](https://textual.textualize.io/).

## Requirements

- Python 3.11+
- pip

## Setup (clean checkout)

```bash
# 1. Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# 2. Install all dependencies
make setup

# 3. Copy credentials file and fill in your Matrix credentials
cp .env.local.example .env.local
# Edit .env.local — set MATRIX_HOMESERVER, MATRIX_USER, MATRIX_PASSWORD
```

## Running

```bash
make run
# or directly:
python -m matrixtui
```

### Credentials

The app reads credentials from `.env.local` in the repo root:

```
MATRIX_HOMESERVER=https://matrix.org
MATRIX_USER=@youruser:matrix.org
MATRIX_PASSWORD=yourpassword
```

## Key bindings

| Key | Action |
|-----|--------|
| Arrow keys / j/k | Navigate room list |
| Enter | Select room |
| Type + Enter | Send message |
| Ctrl+R | Load older message history |
| Ctrl+C | Quit |

## Testing

```bash
# Unit tests only (no credentials needed)
make test

# Tests with coverage report
make coverage        # writes coverage-summary.json

# JUnit XML report
make test-report     # writes junit.xml

# Lint check
make lint
```

Integration tests (marked `@pytest.mark.integration`) require `.env.local` with valid credentials.
They are included in `make test` but will be skipped automatically if credentials are absent.

## Project layout

```
matrixtui/        # application source
  __init__.py
  __main__.py     # entry point
  config.py       # env/credential loading
  client.py       # async Matrix client (matrix-nio wrapper)
  app.py          # Textual TUI application
tests/            # pytest suite
  test_client.py  # unit tests for client logic
  test_config.py  # config loading tests
  test_integration.py  # live homeserver tests
```
