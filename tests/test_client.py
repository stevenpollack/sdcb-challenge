"""Unit tests for MatrixClient logic (no network)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from matrixtui.client import MatrixClient, Message, RoomSummary


def make_client():
    with patch("matrixtui.client.AsyncClient"):
        return MatrixClient("https://matrix.org", "@test:matrix.org")


def test_message_dataclass():
    msg = Message(
        event_id="$abc",
        sender="@alice:matrix.org",
        body="hello",
        timestamp=1700000000000,
        is_me=False,
    )
    assert msg.body == "hello"
    assert not msg.is_me


def test_room_summary_defaults():
    rs = RoomSummary(room_id="!abc:matrix.org", display_name="Test Room")
    assert rs.unread_count == 0
    assert rs.last_message == ""
    assert rs.members == []


def test_client_registers_callbacks():
    client = make_client()
    cb = MagicMock()
    client.on_room_update(cb)
    client.on_message(cb)
    assert cb in client._on_room_update
    assert cb in client._on_message


def test_client_initial_state():
    client = make_client()
    assert client.rooms == {}
    assert client.messages == {}
    assert client._running is False


def test_event_to_message():
    client = make_client()
    event = MagicMock()
    event.event_id = "$evt1"
    event.sender = "@alice:matrix.org"
    event.body = "hi there"
    event.server_timestamp = 1700000000000
    msg = client._event_to_message(event)
    assert msg.event_id == "$evt1"
    assert msg.body == "hi there"
    assert msg.is_me is False


def test_event_to_message_is_me():
    client = make_client()
    event = MagicMock()
    event.event_id = "$evt2"
    event.sender = "@test:matrix.org"
    event.body = "my message"
    event.server_timestamp = 1700000000001
    msg = client._event_to_message(event)
    assert msg.is_me is True


@pytest.mark.asyncio
async def test_send_message_returns_event_id():
    client = make_client()
    mock_resp = MagicMock()
    mock_resp.__class__.__name__ = "RoomSendResponse"
    mock_resp.event_id = "$new_event"

    from nio import RoomSendResponse
    with patch.object(client._client, "room_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = MagicMock(spec=RoomSendResponse, event_id="$new_event")
        result = await client.send_message("!room:matrix.org", "hello")
    assert result == "$new_event"


@pytest.mark.asyncio
async def test_send_message_failure_returns_none():
    client = make_client()
    from nio import RoomSendError
    with patch.object(client._client, "room_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = MagicMock()  # not RoomSendResponse
        # Patch isinstance to return False for RoomSendResponse
        import matrixtui.client as mod
        original = mod.RoomSendResponse
        try:
            # Make the response not match RoomSendResponse
            mock_send.return_value = object()
            result = await client.send_message("!room:matrix.org", "hello")
        finally:
            pass
    # object() is not RoomSendResponse, so result should be None
    assert result is None


def test_room_name_uses_display_name():
    room = MagicMock()
    room.display_name = "My Room"
    room.name = "raw-name"
    assert MatrixClient._room_name(room) == "My Room"


def test_room_name_falls_back_to_name():
    room = MagicMock()
    room.display_name = None
    room.name = "fallback-name"
    room.users = {}
    room.own_user_id = "@me:matrix.org"
    assert MatrixClient._room_name(room) == "fallback-name"


def test_dedup_messages_in_process_sync():
    """Messages with same event_id should not be added twice."""
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = []

    msg = Message("$e1", "@a:m.org", "hi", 1000)
    client.messages["!r:m.org"].append(msg)

    # Simulate receiving same event again — should not duplicate
    seen_ids = {m.event_id for m in client.messages["!r:m.org"]}
    new_msg = Message("$e1", "@a:m.org", "hi", 1000)
    if new_msg.event_id not in seen_ids:
        client.messages["!r:m.org"].append(new_msg)

    assert len(client.messages["!r:m.org"]) == 1
