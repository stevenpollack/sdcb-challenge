"""Integration tests against a live Matrix homeserver.

These tests require .env.local with real credentials. They are marked
`integration` and skipped automatically if credentials are missing.

Covered scenarios per PROMPT.md:
  - Send round-trip: A sends a message, it appears via A's live sync callback.
  - Real-time receive: A sends, B receives within timeout without manual refresh.
  - Reconnect resumes sync: drop B's sync, reconnect, B still receives new messages.
  - Two-party typing: A types, B observes the typing notification.
  - Two-party reactions: B reacts to A's message, A observes the reaction.
  - Two-party read receipts: B sends read receipt, server accepts without error.

Design notes:
  - Session-scoped `client_a` / `client_b` fixtures do one password login each.
  - Per-test fresh clients (needed to get a clean sync position) use `set_token()`
    to avoid additional password-based logins and the resulting rate-limit errors.
"""
from __future__ import annotations

import asyncio
import uuid
import pytest

from matrixclient.client import MatrixClient


pytestmark = pytest.mark.integration

REALTIME_TIMEOUT = 45


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clone_client(source: MatrixClient, device_name: str) -> MatrixClient:
    """Create a new MatrixClient re-using an existing session's access token."""
    c = MatrixClient(source.homeserver, source.user_id, device_name=device_name)
    c.set_token(source.access_token, source.device_id)
    return c


async def _find_or_create_shared_room(client_a: MatrixClient, client_b: MatrixClient) -> str:
    """Return a room ID where both users are joined, creating one if needed."""
    b_id = client_b.user_id
    for room_id, room in client_a.rooms.items():
        if b_id in room.members and len(room.members) >= 2:
            return room_id

    resp = await client_a._nio.room_create(
        name="matrix-tui-test-" + uuid.uuid4().hex[:8],
        invite=[b_id],
    )
    if not hasattr(resp, "room_id"):
        pytest.fail(f"Could not create test room: {resp}")
    room_id: str = resp.room_id

    join_resp = await client_b._nio.join(room_id)
    if not hasattr(join_resp, "room_id"):
        pytest.fail(f"User B could not join test room: {join_resp}")

    await client_a.initial_sync()
    await client_b.initial_sync()
    return room_id


# ---------------------------------------------------------------------------
# Session-scoped fixtures: one password login per user per test session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
async def client_a(homeserver_url, user_a_id, user_a_password):
    c = MatrixClient(homeserver_url, user_a_id, device_name="matrix-tui-test-a")
    await c.login(user_a_password)
    await c.initial_sync()
    yield c
    await c.close()


@pytest.fixture(scope="session")
async def client_b(homeserver_b_url, user_b_id, user_b_password):
    c = MatrixClient(homeserver_b_url, user_b_id, device_name="matrix-tui-test-b")
    await c.login(user_b_password)
    await c.initial_sync()
    yield c
    await c.close()


@pytest.fixture(scope="session")
async def shared_room(client_a, client_b) -> str:
    return await _find_or_create_shared_room(client_a, client_b)


# ---------------------------------------------------------------------------
# Test: send round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_round_trip(client_a, shared_room):
    """A sends a message; A's own live sync callback fires for that message."""
    unique_body = f"test-send-{uuid.uuid4().hex}"

    # Fresh client reusing the session token → no new password login
    a = _clone_client(client_a, "matrix-tui-roundtrip")
    await a.initial_sync()

    received = asyncio.Event()

    def _on_msg(r_id: str, msg):
        if r_id == shared_room and msg.body == unique_body:
            received.set()

    a.on_message(_on_msg)
    a.start_sync()

    try:
        await asyncio.sleep(0.5)
        event_id = await a.send_message(shared_room, unique_body)
        assert event_id is not None, "send_message returned None event_id"
        await asyncio.wait_for(received.wait(), timeout=REALTIME_TIMEOUT)
    finally:
        await a.close()


# ---------------------------------------------------------------------------
# Test: real-time receive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_realtime_receive(client_a, client_b, shared_room):
    """A sends a message; B receives it via live sync without a manual refresh."""
    unique_body = f"test-realtime-{uuid.uuid4().hex}"

    b = _clone_client(client_b, "matrix-tui-realtime-b")
    await b.initial_sync()

    received = asyncio.Event()

    def _on_msg(r_id: str, msg):
        if r_id == shared_room and msg.body == unique_body:
            received.set()

    b.on_message(_on_msg)
    b.start_sync()

    try:
        await asyncio.sleep(0.5)
        event_id = await client_a.send_message(shared_room, unique_body)
        assert event_id is not None
        await asyncio.wait_for(received.wait(), timeout=REALTIME_TIMEOUT)
    finally:
        await b.close()


# ---------------------------------------------------------------------------
# Test: reconnect resumes sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_resumes_sync(client_a, client_b, shared_room):
    """B's sync is stopped; A sends; B reconnects and receives the missed message."""
    unique_body = f"test-reconnect-{uuid.uuid4().hex}"

    b = _clone_client(client_b, "matrix-tui-reconnect")
    await b.initial_sync()

    received = asyncio.Event()

    def _on_msg(r_id: str, msg):
        if r_id == shared_room and msg.body == unique_body:
            received.set()

    b.on_message(_on_msg)
    b.start_sync()
    await asyncio.sleep(0.5)

    # Simulate disconnect: cancel the running sync task
    if b._sync_task:
        b._sync_task.cancel()
        try:
            await b._sync_task
        except asyncio.CancelledError:
            pass
    b._sync_task = None

    # Send while B is "disconnected"
    event_id = await client_a.send_message(shared_room, unique_body)
    assert event_id is not None

    # Reconnect B by restarting sync loop
    b._running = True
    b._sync_task = asyncio.create_task(b._sync_loop())

    try:
        await asyncio.wait_for(received.wait(), timeout=REALTIME_TIMEOUT)
    finally:
        await b.close()


# ---------------------------------------------------------------------------
# Test: two-party typing indicator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_typing_indicator_two_party(client_a, client_b, shared_room):
    """A sends typing=True; B's live sync reports A in the typing list."""
    typing_observed = asyncio.Event()

    b = _clone_client(client_b, "matrix-tui-typing-b")
    await b.initial_sync()

    def _on_typing(r_id: str, users: list[str]):
        if r_id == shared_room and client_a.user_id in users:
            typing_observed.set()

    b.on_typing(_on_typing)
    b.start_sync()
    await asyncio.sleep(0.5)

    try:
        await client_a.send_typing(shared_room, True)
        await asyncio.wait_for(typing_observed.wait(), timeout=REALTIME_TIMEOUT)
    finally:
        await client_a.send_typing(shared_room, False)
        await b.close()


# ---------------------------------------------------------------------------
# Test: two-party reactions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reaction_two_party(client_a, client_b, shared_room):
    """A sends a message; B reacts to it; A observes the reaction via live sync."""
    unique_body = f"test-reaction-{uuid.uuid4().hex}"

    # A sends the message to react to
    event_id = await client_a.send_message(shared_room, unique_body)
    assert event_id is not None
    await asyncio.sleep(1)  # brief pause for server to process

    reaction_observed = asyncio.Event()

    # Fresh A observer: clean sync position so it will see the reaction event
    a_obs = _clone_client(client_a, "matrix-tui-rxn-obs-a")
    await a_obs.initial_sync()

    def _on_room_update(r_id: str, room):
        if r_id != shared_room:
            return
        for msg in room.messages:
            if msg.event_id == event_id and "👍" in msg.reactions:
                reaction_observed.set()

    a_obs.on_room_update(_on_room_update)
    a_obs.start_sync()
    await asyncio.sleep(0.5)

    # B sends the reaction (uses session client, no new login)
    rxn_id = await client_b.send_reaction(shared_room, event_id, "👍")
    assert rxn_id is not None, "B could not send reaction"

    try:
        await asyncio.wait_for(reaction_observed.wait(), timeout=REALTIME_TIMEOUT)
    finally:
        await a_obs.close()


# ---------------------------------------------------------------------------
# Test: two-party read receipts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_receipt_two_party(client_a, client_b, shared_room):
    """A sends a message; B sends a read receipt; server accepts it without error."""
    unique_body = f"test-receipt-{uuid.uuid4().hex}"
    event_id = await client_a.send_message(shared_room, unique_body)
    assert event_id is not None

    await asyncio.sleep(1)

    # B sends read receipt using the session client (no extra login)
    await client_b.send_read_receipt(shared_room, event_id)
    # If the above doesn't raise, the server accepted the receipt
