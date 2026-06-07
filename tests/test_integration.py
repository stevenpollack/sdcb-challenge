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
    """Send a message to the first available room and verify event_id returned."""
    if not _has_credentials():
        pytest.skip("No Matrix credentials in environment")
    client = _shared["client"]
    loop = _shared["loop"]
    if not client.rooms:
        pytest.skip("No rooms available")
    room_id = next(iter(client.rooms))
    event_id = loop.run_until_complete(
        client.send_message(room_id, "matrixtui integration test ping")
    )
    assert event_id is not None, "send_message should return an event_id"
    assert event_id.startswith("$"), f"Unexpected event_id format: {event_id}"
