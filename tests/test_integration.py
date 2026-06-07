"""Integration tests against live matrix.org homeserver.

Requires .env.local with valid MATRIX_USER and MATRIX_PASSWORD.
Skipped automatically when credentials are absent.

All tests share a single login session (module scope) to avoid rate-limiting.
The session is created synchronously in the fixture so nio's AsyncClient is
always used on the loop it was created on.
"""
import asyncio
import os

import pytest

from matrixtui.app import MatrixApp
from matrixtui.client import MatrixClient
from matrixtui.config import Config

pytestmark = pytest.mark.integration


def _has_credentials() -> bool:
    return bool(os.environ.get("MATRIX_USER") and os.environ.get("MATRIX_PASSWORD"))


_shared: dict = {}


@pytest.fixture(scope="module", autouse=True)
def integration_session():
    """Create one login session for the entire module, then tear it down."""
    if not _has_credentials():
        yield
        return

    cfg = Config.from_env()
    client = MatrixClient(cfg.homeserver, cfg.user_id)
    loop = asyncio.new_event_loop()

    loop.run_until_complete(client.login(cfg.password))
    loop.run_until_complete(client.start_sync())
    loop.run_until_complete(asyncio.sleep(2))

    _shared["client"] = client
    _shared["loop"] = loop

    yield

    loop.run_until_complete(client.logout())
    loop.close()
    _shared.clear()


def test_login_succeeds():
    """Verify the shared session has a valid access token."""
    if not _has_credentials():
        pytest.skip("No Matrix credentials in environment")
    client = _shared["client"]
    assert client.nio_client.access_token is not None
    assert len(client.nio_client.access_token) > 0


def test_sync_populates_rooms():
    """After initial sync, at least one room should be visible."""
    if not _has_credentials():
        pytest.skip("No Matrix credentials in environment")
    client = _shared["client"]
    assert len(client.rooms) > 0, "Expected at least one room after sync"


def test_rooms_have_display_names():
    """All synced rooms should have non-empty display names."""
    if not _has_credentials():
        pytest.skip("No Matrix credentials in environment")
    client = _shared["client"]
    for room_id, summary in client.rooms.items():
        assert summary.display_name, f"Room {room_id} has no display name"


def test_send_message_returns_event_id():
    """Send a message to a writable room and verify event_id returned.

    Tries each room in turn until one accepts the message (some rooms have
    power-level restrictions that forbid posting).
    """
    if not _has_credentials():
        pytest.skip("No Matrix credentials in environment")
    client = _shared["client"]
    loop = _shared["loop"]
    if not client.rooms:
        pytest.skip("No rooms available")

    event_id = None
    for room_id in client.rooms:
        event_id = loop.run_until_complete(
            client.send_message(room_id, "matrixtui integration test ping")
        )
        if event_id is not None:
            break

    assert event_id is not None, (
        "send_message should return an event_id from at least one room"
    )
    assert event_id.startswith("$"), f"Unexpected event_id format: {event_id}"


@pytest.mark.asyncio
async def test_app_connects_and_shows_rooms():
    """E2E: MatrixApp starts, logs in, syncs, and renders the room list.

    This test exercises the full _connect() code path against a live homeserver,
    verifying that the TUI actually becomes usable after startup.
    """
    if not _has_credentials():
        pytest.skip("No Matrix credentials in environment")

    cfg = Config.from_env()
    client = MatrixClient(cfg.homeserver, cfg.user_id)

    app = MatrixApp(client)

    async with app.run_test(size=(120, 35)) as pilot:
        # Allow time for login + initial sync (up to 15s)
        for _ in range(30):
            await pilot.pause(0.5)
            from textual.widgets import Static
            status_text = str(app.query_one("#status-bar", Static).content)
            if "Connected" in status_text or "Error" in status_text:
                break

        from textual.widgets import Static
        status_text = str(app.query_one("#status-bar", Static).content)
        assert "Connected" in status_text, (
            f"Expected 'Connected' in status bar, got: {status_text!r}"
        )

        # Room list must be populated after a real sync
        assert len(app._room_items) > 0, "Room list is empty after live sync"

        # Welcome message should be visible (shown on mount before connect)
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        assert log.lines, "Welcome message missing from log pane"

        await app.action_quit()
