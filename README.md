# matrixtui — Matrix Protocol TUI Client

A terminal user interface client for the [Matrix](https://matrix.org) protocol, built with
[Textual](https://textual.textualize.io/) and [matrix-nio](https://github.com/matrix-nio/matrix-nio).

## Features

- Login with password credentials
- Room list sidebar (auto-updates on join/leave)
- Real-time message delivery via `sync_forever` (no manual refresh)
- Send messages with Enter
- Load recent message history when switching rooms
- Join rooms by alias or room ID (`Ctrl+R`)
- Keyboard navigation
- Reconnect / retry on transient sync errors

## Requirements

- Python 3.11+
- `pip3` (system or virtualenv)

## Quick Start (from a clean checkout)

```bash
# 1. Install dependencies
make setup

# 2. Provide credentials
cp .env.local.example .env.local
# Edit .env.local and set MATRIX_HOMESERVER, MATRIX_USER, MATRIX_PASSWORD

# 3. Run the TUI
make run
```

### Manual setup (without Make)

```bash
pip3 install -e ".[dev]"
```

### Running without Make

```bash
python3 -m matrixtui
```

## Credentials

Create `.env.local` in the repo root (it is gitignored):

```
MATRIX_HOMESERVER=https://matrix.org
MATRIX_USER=@youruser:matrix.org
MATRIX_PASSWORD=yourpassword
```

Optionally add a second account for two-party integration tests:

```
MATRIX_HOMESERVER_B=https://matrix.org
MATRIX_USER_B=@seconduser:matrix.org
MATRIX_PASSWORD_B=theirpassword
```

## Make Targets

| Target | Description |
|---|---|
| `make setup` | Install all dependencies |
| `make run` | Launch the TUI |
| `make test` | Run the full test suite (exits non-zero on failure) |
| `make coverage` | Run tests with coverage; writes `coverage-summary.json` |
| `make test-report` | Run tests and emit `junit.xml` |
| `make lint` | No-op lint target (exits 0) |

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Ctrl+Q` | Quit |
| `Ctrl+J` | Focus room list |
| `Ctrl+K` | Focus message input |
| `Ctrl+R` | Join a room by alias or ID |
| `Enter` | Send message / confirm |
| `Escape` | Cancel input |

## Architecture

```
src/matrixtui/
├── __init__.py        # package metadata
├── __main__.py        # python -m matrixtui entry point
├── app.py             # Textual TUI application (MatrixTUIApp)
├── config.py          # .env.local loader
└── matrix_client.py   # matrix-nio wrapper (MatrixClient)

tests/
├── conftest.py            # shared fixtures, .env.local loading
├── test_config.py         # unit tests for config loading
├── test_matrix_client.py  # unit tests for MatrixClient (mocked nio)
└── test_integration.py    # integration tests against the real homeserver
```

### Adding a Feature

1. If it touches Matrix protocol: extend `MatrixClient` in `matrix_client.py`.
2. If it touches the UI: extend `MatrixTUIApp` in `app.py`.
3. Add unit tests in `test_matrix_client.py` (mock nio) and/or `test_config.py`.
4. Add an integration test in `test_integration.py` if it touches the live server.
5. Update `FEATURES.md` with the new feature row.

### Key Design Decisions

- **Thread safety**: `matrix-nio` callbacks run in the sync loop thread. The TUI runs in the
  Textual event loop. All callbacks call `self.call_from_thread(...)` to post updates to the TUI.
- **Single session per run**: Only one login per process. The `_sync_task` runs `sync_forever`
  with exponential backoff on errors — no explicit reconnect timer needed.
- **Rate limiting**: matrix.org enforces ~3 logins/minute per IP. Integration tests share a
  module-scoped session fixture and reuse the access token for fresh clients to stay within limits.
