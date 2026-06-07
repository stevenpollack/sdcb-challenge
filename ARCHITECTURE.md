# Architecture

## Overview

```
matrixtui/
├── __main__.py    # CLI entry point — loads config, constructs MatrixClient + MatrixApp
├── config.py      # Config dataclass — reads MATRIX_* env vars from .env.local
├── client.py      # MatrixClient — async nio wrapper; pure Python, no Textual dependency
└── app.py         # MatrixApp — Textual TUI; consumes MatrixClient via callbacks
```

## Layering

```
.env.local → Config → MatrixClient → (callbacks) → MatrixApp (Textual)
                               ↑
                           matrix-nio (network)
```

`MatrixClient` has **no Textual dependency**. It exposes three callback hooks:

| Method | Signature | Fires when |
|---|---|---|
| `on_room_update(cb)` | `cb(room_id: str)` | Room metadata changes (name, unread, members) |
| `on_message(cb)` | `cb(room_id: str, msg: Message)` | New message arrives |
| `on_typing(cb)` | `cb(room_id: str, users: list[str])` | Typing list changes |

`MatrixApp` bridges these callbacks to Textual's event loop by posting custom
`TMessage` subclasses (`RoomUpdated`, `NewMessage`, `TypingUpdated`) — the only
safe way to update UI state from a background asyncio task.

## Key data types

```python
@dataclass
class Message:
    event_id: str
    sender: str
    body: str          # pre-formatted: images get "[image: …]", emotes get "* …"
    timestamp: int     # milliseconds since epoch
    is_me: bool
    msgtype: str       # "m.text" | "m.image" | "m.file" | "m.video" | "m.audio" | "m.emote" | "m.notice"

@dataclass
class RoomSummary:
    room_id: str
    display_name: str
    unread_count: int
    last_message: str
    last_ts: int
    member_count: int
    members: list[str]
```

## How to add a new feature

### Add a new message type

1. In `client.py::_event_to_message`, add an `elif isinstance(event, RoomMessageXxx)` branch.
2. Add a colour entry in `app.py::_MSGTYPE_COLOUR` if you want distinct rendering.

### Add a new event type (e.g. reactions, redactions)

1. Import the nio event class in `client.py`.
2. Register a callback: `self._client.add_event_callback(self._on_xyz, XyzEvent)`.
3. Implement `async def _on_xyz(self, room, event)`.
4. Fire `self._on_room_update` callbacks so the UI refreshes.

### Add a new UI panel

1. Add a new widget in `app.py::compose()`.
2. Subscribe to the appropriate `MatrixClient` callback.
3. Post a new `TMessage` subclass from the callback and handle it in `on_<message_name>`.

### Add a slash command

Parse the message text in `on_input_submitted` before calling `send_message`:
```python
if text.startswith("/join "):
    room_alias = text[6:].strip()
    await self._client.join_room(room_alias)
    return
```

## Testing

- **Unit tests** (`tests/test_client.py`, `tests/test_config.py`): mock `AsyncClient`
  at construction time via `patch("matrixtui.client.AsyncClient")`. No network needed.
- **Integration tests** (`tests/test_integration.py`): marked `@pytest.mark.integration`.
  Require `.env.local`. Share one login session across the module to avoid rate-limits.
  Run with `pytest tests/test_integration.py` or included automatically in `make test`.

## Dependency notes

- `matrix-nio` without `[e2e]` extra — avoids native `python-olm` / CMake build.
  E2E encryption is not currently supported; add `[e2e]` and handle `OlmEncryptedEvent`
  callbacks to enable it.
- `textual >= 0.61` — uses `RichLog`, `ListView`, `run_worker`. Do not downgrade.
