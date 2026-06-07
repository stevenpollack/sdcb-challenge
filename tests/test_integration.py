"""Integration tests against live matrix.org homeserver.

Requires .env.local with valid MATRIX_USER and MATRIX_PASSWORD.
Skipped automatically when credentials are absent.
"""
import os
import pytest
import asyncio

from matrixtui.config import Config
from matrixtui.client import MatrixClient

# Skip all tests in this module if credentials are not present
pytestmark = pytest.mark.integration


def _has_credentials() -> bool:
    return bool(os.environ.get("MATRIX_USER") and os.environ.get("MATRIX_PASSWORD"))


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def live_client():
    if not _has_credentials():
        pytest.skip("No Matrix credentials in environment")
    cfg = Config.from_env()
    client = MatrixClient(cfg.homeserver, cfg.user_id)
    await client.login(cfg.password)
    yield client
    await client.logout()


@pytest.mark.asyncio
async def test_login_succeeds(live_client):
    """Verify we can log in and the client has a valid access token."""
    assert live_client.nio_client.access_token is not None
    assert len(live_client.nio_client.access_token) > 0


@pytest.mark.asyncio
async def test_sync_populates_rooms(live_client):
    """After initial sync, at least one room should be visible."""
    await live_client.start_sync()
    # Give sync a moment to settle
    await asyncio.sleep(2)
    assert len(live_client.rooms) > 0, "Expected at least one room after sync"


@pytest.mark.asyncio
async def test_rooms_have_display_names(live_client):
    """All synced rooms should have non-empty display names."""
    for room_id, summary in live_client.rooms.items():
        assert summary.display_name, f"Room {room_id} has no display name"


@pytest.mark.asyncio
async def test_send_and_receive_message(live_client):
    """Send a message to the first available room and verify event_id returned."""
    if not live_client.rooms:
        pytest.skip("No rooms available")
    room_id = next(iter(live_client.rooms))
    event_id = await live_client.send_message(room_id, "matrixtui integration test ping")
    assert event_id is not None, "send_message should return an event_id"
    assert event_id.startswith("$"), f"Unexpected event_id format: {event_id}"
