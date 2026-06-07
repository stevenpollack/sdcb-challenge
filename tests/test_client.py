"""Unit tests for MatrixClient logic (no network)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from matrixtui.client import MatrixClient, Message, RoomSummary


def make_client():
    with patch("matrixtui.client.AsyncClient"):
        return MatrixClient("https://matrix.org", "@test:matrix.org")


def make_event(
    event_id="$e1",
    sender="@alice:matrix.org",
    body="hello",
    ts=1700000000000,
    cls=None,
):
    from nio import RoomMessageText
    cls = cls or RoomMessageText
    event = MagicMock(spec=cls)
    event.event_id = event_id
    event.sender = sender
    event.body = body
    event.server_timestamp = ts
    return event


# ------------------------------------------------------------------
# Dataclasses
# ------------------------------------------------------------------

def test_message_defaults():
    msg = Message(event_id="$x", sender="@a:m.org", body="hi", timestamp=0)
    assert msg.is_me is False
    assert msg.msgtype == "m.text"


def test_room_summary_defaults():
    rs = RoomSummary(room_id="!r:m.org", display_name="Test")
    assert rs.unread_count == 0
    assert rs.last_message == ""
    assert rs.member_count == 0
    assert rs.members == []


# ------------------------------------------------------------------
# Client init and callbacks
# ------------------------------------------------------------------

def test_client_initial_state():
    client = make_client()
    assert client.rooms == {}
    assert client.messages == {}
    assert client.typing_users == {}
    assert client._running is False


def test_client_registers_callbacks():
    client = make_client()
    cb = MagicMock()
    client.on_room_update(cb)
    client.on_message(cb)
    client.on_typing(cb)
    assert cb in client._on_room_update
    assert cb in client._on_message
    assert cb in client._on_typing


# ------------------------------------------------------------------
# _event_to_message
# ------------------------------------------------------------------

def test_event_to_message_text():
    client = make_client()
    from nio import RoomMessageText
    event = make_event(cls=RoomMessageText)
    msg = client._event_to_message(event)
    assert msg.event_id == "$e1"
    assert msg.body == "hello"
    assert msg.msgtype == "m.text"
    assert msg.is_me is False


def test_event_to_message_is_me():
    client = make_client()
    from nio import RoomMessageText
    event = make_event(sender="@test:matrix.org", cls=RoomMessageText)
    msg = client._event_to_message(event)
    assert msg.is_me is True


def test_event_to_message_image():
    client = make_client()
    from nio import RoomMessageImage
    event = make_event(body="photo.jpg", cls=RoomMessageImage)
    msg = client._event_to_message(event)
    assert msg.msgtype == "m.image"
    assert msg.body == "[image: photo.jpg]"


def test_event_to_message_file():
    client = make_client()
    from nio import RoomMessageFile
    event = make_event(body="doc.pdf", cls=RoomMessageFile)
    msg = client._event_to_message(event)
    assert msg.msgtype == "m.file"
    assert "[file:" in msg.body


def test_event_to_message_video():
    client = make_client()
    from nio import RoomMessageVideo
    event = make_event(body="clip.mp4", cls=RoomMessageVideo)
    msg = client._event_to_message(event)
    assert msg.msgtype == "m.video"


def test_event_to_message_audio():
    client = make_client()
    from nio import RoomMessageAudio
    event = make_event(body="track.mp3", cls=RoomMessageAudio)
    msg = client._event_to_message(event)
    assert msg.msgtype == "m.audio"


def test_event_to_message_emote():
    client = make_client()
    from nio import RoomMessageEmote
    event = make_event(body="waves hello", cls=RoomMessageEmote)
    msg = client._event_to_message(event)
    assert msg.msgtype == "m.emote"
    assert msg.body.startswith("* ")


def test_event_to_message_notice():
    client = make_client()
    from nio import RoomMessageNotice
    event = make_event(body="bot output", cls=RoomMessageNotice)
    msg = client._event_to_message(event)
    assert msg.msgtype == "m.notice"
    assert msg.body == "bot output"


# ------------------------------------------------------------------
# _room_name
# ------------------------------------------------------------------

def test_room_name_display_name():
    room = MagicMock()
    room.display_name = "My Room"
    assert MatrixClient._room_name(room) == "My Room"


def test_room_name_falls_back_to_name():
    room = MagicMock()
    room.display_name = None
    room.name = "fallback"
    room.users = {}
    room.own_user_id = "@me:m.org"
    assert MatrixClient._room_name(room) == "fallback"


def test_room_name_dm_uses_other_user_display():
    room = MagicMock()
    room.display_name = None
    room.name = None
    other = MagicMock()
    other.display_name = "Alice"
    room.users = {"@alice:m.org": other}
    room.own_user_id = "@me:m.org"
    assert MatrixClient._room_name(room) == "Alice"


def test_room_name_dm_no_display_falls_back_to_user_id():
    room = MagicMock()
    room.display_name = None
    room.name = None
    other = MagicMock()
    other.display_name = None
    room.users = {"@alice:m.org": other}
    room.own_user_id = "@me:m.org"
    assert MatrixClient._room_name(room) == "@alice:m.org"


def test_room_name_empty_room():
    room = MagicMock()
    room.display_name = None
    room.name = None
    room.users = {}
    room.own_user_id = "@me:m.org"
    room.room_id = "!empty:m.org"
    assert MatrixClient._room_name(room) == "!empty:m.org"


# ------------------------------------------------------------------
# send_message
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_message_returns_event_id():
    client = make_client()
    from nio import RoomSendResponse
    with patch.object(client._client, "room_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = MagicMock(spec=RoomSendResponse, event_id="$new")
        result = await client.send_message("!r:m.org", "hello")
    assert result == "$new"


@pytest.mark.asyncio
async def test_send_message_failure_returns_none():
    client = make_client()
    with patch.object(client._client, "room_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = object()
        result = await client.send_message("!r:m.org", "hello")
    assert result is None


# ------------------------------------------------------------------
# send_read_receipt
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_read_receipt_calls_markers():
    client = make_client()
    with patch.object(
        client._client, "room_read_markers", new_callable=AsyncMock
    ) as mock_rm:
        await client.send_read_receipt("!r:m.org", "$evt")
        mock_rm.assert_called_once_with(
            room_id="!r:m.org",
            fully_read_event="$evt",
            read_event="$evt",
        )


@pytest.mark.asyncio
async def test_send_read_receipt_swallows_exceptions():
    client = make_client()
    with patch.object(
        client._client, "room_read_markers", new_callable=AsyncMock, side_effect=Exception("fail")
    ):
        # Should not raise
        await client.send_read_receipt("!r:m.org", "$evt")


# ------------------------------------------------------------------
# load_history
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_history_returns_empty_on_error():
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    nio_room = MagicMock()
    nio_room.prev_batch = "t123"
    client._client.rooms = {"!r:m.org": nio_room}
    with patch.object(client._client, "room_messages", new_callable=AsyncMock) as mock_rm:
        mock_rm.return_value = object()  # not RoomMessagesResponse
        result = await client.load_history("!r:m.org")
    assert result == []


@pytest.mark.asyncio
async def test_load_history_prepends_messages():
    client = make_client()
    from nio import RoomMessageText, RoomMessagesResponse
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    nio_room = MagicMock()
    nio_room.prev_batch = "t123"
    client._client.rooms = {"!r:m.org": nio_room}

    old_event = make_event(event_id="$old", ts=999, cls=RoomMessageText)
    mock_resp = MagicMock(spec=RoomMessagesResponse)
    mock_resp.chunk = [old_event]

    with patch.object(client._client, "room_messages", new_callable=AsyncMock) as mock_rm:
        mock_rm.return_value = mock_resp
        # Seed existing message with newer ts
        client.messages["!r:m.org"] = [
            Message("$new", "@a:m.org", "hi", 1000)
        ]
        result = await client.load_history("!r:m.org")

    assert len(result) == 1
    assert result[0].event_id == "$old"
    # Prepended: old comes first
    assert client.messages["!r:m.org"][0].event_id == "$old"


@pytest.mark.asyncio
async def test_load_history_deduplicates():
    client = make_client()
    from nio import RoomMessageText, RoomMessagesResponse
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    nio_room = MagicMock()
    nio_room.prev_batch = "t123"
    client._client.rooms = {"!r:m.org": nio_room}

    event = make_event(event_id="$dup", ts=500, cls=RoomMessageText)
    mock_resp = MagicMock(spec=RoomMessagesResponse)
    mock_resp.chunk = [event]

    with patch.object(client._client, "room_messages", new_callable=AsyncMock) as mock_rm:
        mock_rm.return_value = mock_resp
        client.messages["!r:m.org"] = [Message("$dup", "@a:m.org", "hi", 500)]
        result = await client.load_history("!r:m.org")

    assert result == []  # nothing new
    assert len(client.messages["!r:m.org"]) == 1  # no duplicate


# ------------------------------------------------------------------
# Dedup via _on_room_message callback
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_room_message_dedup():
    client = make_client()
    from nio import RoomMessageText
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = []

    room = MagicMock()
    room.room_id = "!r:m.org"

    event = make_event(cls=RoomMessageText)
    await client._on_room_message(room, event)
    await client._on_room_message(room, event)  # duplicate

    assert len(client.messages["!r:m.org"]) == 1


@pytest.mark.asyncio
async def test_on_room_message_fires_callbacks():
    client = make_client()
    from nio import RoomMessageText
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = []
    cb = MagicMock()
    client.on_message(cb)

    room = MagicMock()
    room.room_id = "!r:m.org"
    event = make_event(cls=RoomMessageText)
    await client._on_room_message(room, event)

    cb.assert_called_once()
    args = cb.call_args[0]
    assert args[0] == "!r:m.org"
    assert isinstance(args[1], Message)


# ------------------------------------------------------------------
# Typing notices
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_typing_notice_stores_other_users():
    client = make_client()
    cb = MagicMock()
    client.on_typing(cb)

    room = MagicMock()
    room.room_id = "!r:m.org"

    event = MagicMock()
    event.users = ["@alice:m.org", "@test:matrix.org"]  # self should be filtered
    await client._on_typing_notice(room, event)

    assert client.typing_users["!r:m.org"] == ["@alice:m.org"]
    cb.assert_called_once_with("!r:m.org", ["@alice:m.org"])


@pytest.mark.asyncio
async def test_on_typing_notice_empty():
    client = make_client()
    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock()
    event.users = []
    await client._on_typing_notice(room, event)
    assert client.typing_users["!r:m.org"] == []


# ------------------------------------------------------------------
# _process_sync
# ------------------------------------------------------------------

def test_process_sync_creates_rooms():
    client = make_client()
    nio_room = MagicMock()
    nio_room.display_name = "Test Room"
    nio_room.name = None
    nio_room.users = {}
    nio_room.own_user_id = "@test:matrix.org"
    nio_room.unread_notifications = 3
    nio_room.member_count = 5
    client._client.rooms = {"!r:m.org": nio_room}

    resp = MagicMock()
    client._process_sync(resp)

    assert "!r:m.org" in client.rooms
    assert client.rooms["!r:m.org"].display_name == "Test Room"
    assert client.rooms["!r:m.org"].unread_count == 3
    assert client.rooms["!r:m.org"].member_count == 5


def test_process_sync_updates_existing_room():
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Old Name")
    nio_room = MagicMock()
    nio_room.display_name = "New Name"
    nio_room.unread_notifications = 0
    nio_room.member_count = 2
    client._client.rooms = {"!r:m.org": nio_room}

    client._process_sync(MagicMock())

    assert client.rooms["!r:m.org"].display_name == "New Name"
    assert client.rooms["!r:m.org"].member_count == 2


def test_process_sync_fires_room_update_callbacks():
    client = make_client()
    cb = MagicMock()
    client.on_room_update(cb)
    nio_room = MagicMock()
    nio_room.display_name = "Room"
    nio_room.unread_notifications = 0
    nio_room.member_count = 1
    client._client.rooms = {"!r:m.org": nio_room}
    client._process_sync(MagicMock())
    cb.assert_called_with("!r:m.org")


# ------------------------------------------------------------------
# logout
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_without_login_does_not_raise():
    client = make_client()
    client._client.access_token = None
    client._client.close = AsyncMock()
    await client.logout()
    client._client.close.assert_called_once()


@pytest.mark.asyncio
async def test_logout_cancels_sync_task():
    client = make_client()
    client._client.access_token = None
    client._client.close = AsyncMock()

    async def never_ending():
        import asyncio
        await asyncio.sleep(9999)

    import asyncio
    client._running = True
    client._sync_task = asyncio.create_task(never_ending())
    await client.logout()
    assert client._sync_task.cancelled()
