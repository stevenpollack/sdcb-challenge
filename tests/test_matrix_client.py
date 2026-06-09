"""Unit tests for MatrixClient (using mocks — no live server)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from matrixtui.matrix_client import MatrixClient, Message, Room, MatrixClientError


@pytest.fixture
def mock_nio_client():
    with patch("matrixtui.matrix_client.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.rooms = {}
        MockClient.return_value = instance
        yield instance


@pytest.fixture
def client(mock_nio_client):
    c = MatrixClient(
        homeserver="https://example.com",
        user_id="@alice:example.com",
        password="secret",
    )
    return c


@pytest.mark.asyncio
async def test_login_success(client, mock_nio_client):
    from nio import LoginResponse
    resp = MagicMock(spec=LoginResponse)
    mock_nio_client.login.return_value = resp

    await client.login()

    mock_nio_client.login.assert_called_once_with("secret")
    assert client.connected is True


@pytest.mark.asyncio
async def test_login_failure_raises(client, mock_nio_client):
    mock_nio_client.login.return_value = MagicMock()  # not a LoginResponse

    with pytest.raises(MatrixClientError):
        await client.login()

    assert client.connected is False


@pytest.mark.asyncio
async def test_send_message_success(client, mock_nio_client):
    from nio import RoomSendResponse
    resp = MagicMock(spec=RoomSendResponse)
    resp.event_id = "$abc123"
    mock_nio_client.room_send.return_value = resp

    event_id = await client.send_message("!room:example.com", "Hello")

    mock_nio_client.room_send.assert_called_once()
    call_kwargs = mock_nio_client.room_send.call_args
    assert call_kwargs[1]["room_id"] == "!room:example.com"
    assert call_kwargs[1]["content"]["body"] == "Hello"
    assert event_id == "$abc123"


@pytest.mark.asyncio
async def test_send_message_failure_raises(client, mock_nio_client):
    mock_nio_client.room_send.return_value = MagicMock()  # not RoomSendResponse

    with pytest.raises(MatrixClientError):
        await client.send_message("!room:example.com", "Hello")


@pytest.mark.asyncio
async def test_get_rooms_returns_list(client, mock_nio_client):
    from nio import JoinedRoomsResponse
    resp = MagicMock(spec=JoinedRoomsResponse)
    resp.rooms = ["!room1:example.com", "!room2:example.com"]
    mock_nio_client.joined_rooms.return_value = resp

    # Mock internal room data
    mock_room1 = MagicMock()
    mock_room1.display_name = "General"
    mock_room1.member_count = 5
    mock_room2 = MagicMock()
    mock_room2.display_name = "Dev"
    mock_room2.member_count = 3
    mock_nio_client.rooms = {
        "!room1:example.com": mock_room1,
        "!room2:example.com": mock_room2,
    }

    rooms = await client.get_rooms()

    assert len(rooms) == 2
    names = {r.display_name for r in rooms}
    assert "General" in names
    assert "Dev" in names


def test_get_display_name():
    c = MatrixClient("https://example.com", "@alice:example.com", "pw")
    assert c.get_display_name("@alice:example.com") == "alice"
    assert c.get_display_name("@bob:matrix.org") == "bob"


@pytest.mark.asyncio
async def test_join_room_success(client, mock_nio_client):
    from nio import JoinResponse
    resp = MagicMock(spec=JoinResponse)
    resp.room_id = "!newroom:example.com"
    mock_nio_client.join.return_value = resp
    mock_nio_client.rooms = {}

    room_id = await client.join_room("#general:example.com")

    mock_nio_client.join.assert_called_once_with("#general:example.com")
    assert room_id == "!newroom:example.com"


@pytest.mark.asyncio
async def test_join_room_failure_raises(client, mock_nio_client):
    mock_nio_client.join.return_value = MagicMock()  # not JoinResponse

    with pytest.raises(MatrixClientError):
        await client.join_room("#nope:example.com")


@pytest.mark.asyncio
async def test_on_message_callback_fires(mock_nio_client):
    received = []

    def on_msg(msg: Message):
        received.append(msg)

    from nio import LoginResponse
    mock_nio_client.login.return_value = MagicMock(spec=LoginResponse)

    c = MatrixClient(
        homeserver="https://example.com",
        user_id="@alice:example.com",
        password="secret",
        on_message=on_msg,
    )
    mock_nio_client.rooms = {}

    # Simulate callback invocation
    from nio import MatrixRoom, RoomMessageText
    room = MagicMock(spec=MatrixRoom)
    room.room_id = "!room:example.com"
    event = MagicMock(spec=RoomMessageText)
    event.sender = "@bob:example.com"
    event.body = "hi there"
    event.event_id = "$ev1"
    event.server_timestamp = 1700000000000

    # Patch joined_rooms to return empty
    from nio import JoinedRoomsResponse
    jr = MagicMock(spec=JoinedRoomsResponse)
    jr.rooms = []
    mock_nio_client.joined_rooms.return_value = jr

    await c._on_room_message(room, event)

    assert len(received) == 1
    assert received[0].body == "hi there"
    assert received[0].sender == "@bob:example.com"


@pytest.mark.asyncio
async def test_stop_cancels_sync(client, mock_nio_client):
    # Create a never-ending sync task
    async def fake_sync_forever():
        await asyncio.sleep(999)

    mock_nio_client.sync_forever = fake_sync_forever
    mock_nio_client.add_event_callback = MagicMock()
    mock_nio_client.close = AsyncMock()

    await client.start_sync()
    assert client._sync_task is not None
    await client.stop()

    assert client._sync_task.cancelled() or client._sync_task.done()
    assert client.connected is False
