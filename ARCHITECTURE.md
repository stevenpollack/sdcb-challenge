# Architecture

## Overview

```
matrixtui/
├── __main__.py    # CLI entry point — loads session or logs in; constructs client + app
├── config.py      # Config dataclass — reads MATRIX_* env vars from .env.local
├── session.py     # Session persistence — save/load/clear ~/.config/matrixtui/session.json
├── client.py      # MatrixClient — async nio wrapper; zero Textual dependency
└── app.py         # MatrixApp — Textual TUI; consumes MatrixClient via callbacks
```

## Layering

```
.env.local → Config → MatrixClient ──(callbacks)──► MatrixApp (Textual)
                            │
                     matrix-nio (network)
                            │
              ~/.config/matrixtui/session.json
```

`MatrixClient` has **no Textual dependency**. All UI updates flow through a
callback → `TMessage` bridge so that background asyncio tasks never touch
Textual widgets directly.

## Callback hooks

| Registration method | Callback signature | Fires when |
|---|---|---|
| `on_room_update(cb)` | `cb(room_id: str)` | Room metadata changes (name, unread, members) |
| `on_message(cb)` | `cb(room_id: str, msg: Message)` | New message arrives |
| `on_typing(cb)` | `cb(room_id: str, users: list[str])` | Typing list changes |
| `on_invite(cb)` | `cb(room_id: str, inviter: str)` | Incoming room invite |

## TMessage bridge (thread-safety)

nio callbacks fire in the asyncio sync loop, not the Textual event loop.
`MatrixApp` wraps each callback with a `post_message()` call:

```python
# In MatrixApp.on_mount:
self._client.on_message(self._schedule_new_message)

def _schedule_new_message(self, room_id: str, msg: Message) -> None:
    self.post_message(NewMessage(room_id, msg))   # thread-safe

def on_new_message(self, event: NewMessage) -> None:
    if self.current_room == event.room_id:
        self._append_message(event.msg)           # runs in Textual event loop
```

Custom `TMessage` subclasses live at the top of `app.py`:
`RoomUpdated`, `NewMessage`, `TypingUpdated`, `InviteReceived`.

## Key data types

```python
@dataclass
class Message:
    event_id: str
    sender: str
    body: str          # pre-formatted: images → "[image: …]", emotes → "* …"
    timestamp: int     # milliseconds since epoch
    is_me: bool
    msgtype: str       # "m.text" | "m.image" | "m.file" | "m.video" |
                       # "m.audio" | "m.emote" | "m.notice" | "m.redacted"
    mentions_me: bool  # True when body contains the local user's MXID or localpart

@dataclass
class RoomSummary:
    room_id: str
    display_name: str
    unread_count: int
    last_message: str
    last_ts: int        # used for sorting rooms by most recent activity
    member_count: int
    members: list[str]
```

## How to add a new feature

### Add a new message type

1. In `client.py::_event_to_message`, add an `elif isinstance(event, RoomMessageXxx)` branch.
2. Add a colour entry in `app.py::_MSGTYPE_COLOUR` if you want distinct rendering.

### Add a new event type (e.g. reactions, polls)

1. Import the nio event class in `client.py`.
2. Register: `self._client.add_event_callback(self._on_xyz, XyzEvent)`.
3. Implement `async def _on_xyz(self, room: MatrixRoom, event: XyzEvent)`.
4. Fire `_on_room_update` callbacks so the UI refreshes.

### Add a slash command

1. Add a method on `MatrixClient` (see pattern below).
2. Add a handler method `_handle_xyz` on `MatrixApp`.
3. Dispatch in `on_input_submitted` before the plain-message `else` branch.
4. Add an entry to `_handle_help` and `FEATURES.md`.

### Add a client API call (standard pattern)

Return `bool` for success/failure; `str | None` for lookups. Always swallow
exceptions with `logger.warning` so the UI never crashes on transient errors:

```python
async def do_thing(self, room_id: str, arg: str) -> bool:
    try:
        from nio import ThingResponse
        resp = await self._client.do_nio_thing(room_id, arg)
        return isinstance(resp, ThingResponse)
    except Exception as exc:
        logger.warning("do_thing error: %s", exc)
    return False
```

### Add a new UI panel

1. Add a widget in `MatrixApp.compose()` and CSS in `MatrixApp.CSS`.
2. Subscribe to the relevant `MatrixClient` callback in `on_mount`.
3. Post a new `TMessage` subclass and handle it in `on_<message_name>`.

## Testing patterns

### Client unit tests (`tests/test_client.py`)

Mock `AsyncClient` at construction time — no network needed:

```python
def make_client():
    with patch("matrixtui.client.AsyncClient"):
        return MatrixClient("https://matrix.org", "@test:matrix.org")

@pytest.mark.asyncio
async def test_do_thing_success():
    from nio import ThingResponse
    client = make_client()
    client._client.do_nio_thing = AsyncMock(return_value=ThingResponse())
    assert await client.do_thing("!r:m.org", "arg") is True
```

### App UI tests (`tests/test_app.py`)

Override `_connect` to skip live login; drive UI with Textual's pilot:

```python
def make_app():
    client = make_client_with_rooms()
    app = MatrixApp(client)
    async def fake_connect():
        app.query_one("#status-bar").update("Connected as @test:matrix.org")
        app._rebuild_room_list()
    app._connect = fake_connect
    return app, client

@pytest.mark.asyncio
async def test_something():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        # drive UI here
        from textual.widgets import Static
        assert "text" in str(app.query_one("#status-bar", Static).content)
```

Key pilot/widget facts:
- `Input.insert_text_at_cursor(text)` — set input value (not `pilot.type()`)
- `Static.content` — get rendered text (not `.renderable`)
- `RichLog.lines` — list of rendered lines (not `._lines`)
- `await pilot.press("enter")` — submit input
- `await pilot.pause(0.2)` — allow Textual event loop to process

### Integration tests (`tests/test_integration.py`)

Marked `@pytest.mark.integration`; skipped unless `.env.local` has valid credentials.
Share one client session across the module with a module-scoped fixture to avoid
rate-limiting. Include at least one `test_app_connects_and_shows_rooms` test that
runs the full `MatrixApp` TUI against the live homeserver.

## Session persistence

`session.py` provides three functions:
- `save_session(homeserver, user_id, access_token, device_id)` — writes JSON, mode 0o600
- `load_session()` — returns `dict | None`
- `clear_session()` — deletes the file (used by `/logout`)

`__main__.py` calls `load_session()` on startup; if found, calls `client.restore_session()`
(sync, just sets attributes) instead of `client.login()`.

## Dependency notes

- `matrix-nio` without `[e2e]` extra — avoids native `python-olm` / CMake build.
  E2E encryption is not supported; add `[e2e]` and handle `OlmEncryptedEvent`
  callbacks to enable it.
- `textual >= 0.61` — uses `RichLog`, `ListView`, `run_worker`. Do not downgrade.
- `pytest-asyncio` with `asyncio_mode = "auto"` (set in `pyproject.toml`) — all
  `async def test_*` functions run automatically without `@pytest.mark.asyncio`.
