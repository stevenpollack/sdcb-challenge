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

Sessions are persisted to `~/.config/matrixtui/session.json` (mode 0o600) after
the first login so subsequent starts restore the session without re-authenticating.
Use `/logout` to invalidate the session and clear this file.

## Key bindings

| Key | Action |
|-----|--------|
| Arrow keys | Navigate room list |
| Enter | Select room |
| Type + Enter | Send message |
| Ctrl+F | Focus room filter |
| Ctrl+N | Jump to next room with unread messages |
| Ctrl+R | Load older message history |
| Esc | Focus message input |
| Ctrl+C | Quit |

## Slash commands

Type any of these in the message input and press Enter:

### Navigation & rooms
| Command | Description |
|---------|-------------|
| `/help` | Show all commands and keybindings |
| `/join #alias:server` | Join a room by alias or room ID |
| `/leave` | Leave the current room |
| `/forget` | Forget a previously left room (removes from server history) |
| `/create <name>` | Create a new private room |
| `/dm <@user:srv>` | Open a direct message room with a user |
| `/rename <name>` | Rename the current room |
| `/settopic <text>` | Set the topic for the current room |
| `/alias #alias:srv` | Publish a local alias for the current room |
| `/resolve #alias:srv` | Resolve a room alias to its room ID |

### Messaging
| Command | Description |
|---------|-------------|
| `/me <action>` | Send an emote (renders as `* username action`) |
| `/react <emoji>` | React to the last message in the current room |
| `/search <query>` | Search all loaded messages by body or sender |
| `/clear` | Clear the message pane |

### Members & moderation
| Command | Description |
|---------|-------------|
| `/members` | List members of the current room (from cache) |
| `/joined` | Fetch live member list from server |
| `/invite <@user:srv>` | Invite a user to the current room |
| `/kick <@user:srv>` | Kick a user from the current room |
| `/ban <@user:srv>` | Ban a user from the current room |
| `/unban <@user:srv>` | Unban a user from the current room |
| `/powerlevel [@user]` | Show power level of self or a given user |

### Profile & presence
| Command | Description |
|---------|-------------|
| `/nick <name>` | Set your global display name |
| `/setavatar <mxc://>` | Set your avatar to an mxc:// URI |
| `/whois <@user:srv>` | Show a user's display name and avatar URL |
| `/presence online\|offline\|unavailable` | Set your presence status |
| `/getpresence <@user>` | Show a user's presence status |

### Utilities
| Command | Description |
|---------|-------------|
| `/topic` | Show the current room topic |
| `/mxcurl <mxc://>` | Convert an mxc:// media URI to an HTTP download URL |
| `/stats` | Show local cache statistics |
| `/logout` | Log out and clear the saved session |

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
  __main__.py     # entry point: loads session or logs in, launches MatrixApp
  config.py       # Config dataclass: reads MATRIX_* env vars
  client.py       # MatrixClient: async nio wrapper, no Textual dependency
  app.py          # MatrixApp: Textual TUI, consumes MatrixClient via callbacks
  session.py      # Session persistence: save/load/clear ~/.config/matrixtui/session.json
tests/            # pytest suite
  test_client.py  # unit tests for MatrixClient (300+ tests, no network)
  test_app.py     # Textual pilot tests for MatrixApp UI
  test_config.py  # config loading tests
  test_integration.py  # live homeserver E2E tests
```
