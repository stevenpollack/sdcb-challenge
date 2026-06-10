# Matrix TUI

A terminal UI client for the [Matrix](https://matrix.org) protocol, built with
[Textual](https://textual.textualize.io/) and [matrix-nio](https://github.com/poljar/matrix-nio).

## Requirements

- Python 3.11+
- pip

## Setup

```bash
# From a clean checkout:
make setup
# or equivalently:
pip install -e ".[dev]"
```

## Configuration

Copy your credentials into `.env.local` at the project root:

```ini
MATRIX_HOMESERVER=https://matrix.org
MATRIX_USER=@youruser:matrix.org
MATRIX_PASSWORD=yourpassword
MATRIX_HOMESERVER_B=https://matrix.org
MATRIX_USER_B=@seconduser:matrix.org
MATRIX_PASSWORD_B=secondpassword
```

`.env.local` is loaded automatically on startup and during tests. It is git-ignored.

## Running

```bash
make run
# or:
python -m matrixclient.main
```

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+Q` | Quit |
| `Ctrl+J` | Select next room |
| `Ctrl+K` | Select previous room |
| `Ctrl+L` | Focus message input |
| `Escape` | Focus room list |
| `F5` | Load older messages |
| `Enter` (in input) | Send message |

## Features

- Login with password; session established via matrix-nio
- Room list with display names
- Real-time message sync (long-poll)
- Send text messages
- Typing indicator — shown for other users, sent while you type
- Reactions (send via API; displayed inline on messages)
- Read receipts (sent on room selection; two-party tested)
- Message redaction (delete) — shown as `[Message deleted]`
- Message editing — edited content shown in place
- Load older messages (F5)
- Automatic reconnect on sync failure

## Tests

```bash
# All tests (unit + integration):
make test

# With coverage report:
make coverage

# JUnit XML:
make test-report
```

Integration tests require `.env.local` with both A and B credentials. They hit the live
`matrix.org` homeserver.

## Architecture

```
src/matrixclient/
  config.py   — loads credentials from .env.local
  client.py   — async Matrix client wrapping matrix-nio (sync loop, send, reactions, …)
  app.py      — Textual TUI: room list, message pane, input, typing bar
  main.py     — entry point

tests/
  conftest.py          — shared fixtures (logged-in clients, shared room)
  test_client_unit.py  — unit tests for data models
  test_integration.py  — live-server integration tests
```

### Extending the client

To add a new feature:

1. **Protocol layer** (`client.py`): add a method to `MatrixClient` (e.g. `async def send_foo()`).
   Register any new nio callbacks in `_register_callbacks()`.
2. **UI layer** (`app.py`): add a new `TxtMessage` subclass, a handler (`on_<message_class>`),
   and any new widgets. Wire them to the client callback via `post_message()`.
3. **Tests**: add a unit test in `test_client_unit.py` and an integration test in
   `test_integration.py` (mark with `@pytest.mark.integration`).
4. **FEATURES.md**: append a row with honest status.

The `MatrixClient` exposes callback registration (`on_message`, `on_room_update`, `on_typing`,
`on_read_receipt`) — subscribe any number of handlers without touching existing code.

## Logs

Runtime logs are written to `matrix-tui.log` in the working directory.
