"""Unit tests for MatrixClient logic (no network)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    assert msg.mentions_me is False


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
    assert msg.mentions_me is False


def test_event_to_message_is_me():
    client = make_client()
    from nio import RoomMessageText
    event = make_event(sender="@test:matrix.org", cls=RoomMessageText)
    msg = client._event_to_message(event)
    assert msg.is_me is True


def test_event_to_message_mentions_me_by_localpart():
    client = make_client()
    from nio import RoomMessageText
    # Body mentions the local user's localpart ("test")
    event = make_event(body="hey test, what do you think?", cls=RoomMessageText)
    msg = client._event_to_message(event)
    assert msg.mentions_me is True


def test_event_to_message_mentions_me_by_mxid():
    client = make_client()
    from nio import RoomMessageText
    event = make_event(body="ping @test:matrix.org please reply", cls=RoomMessageText)
    msg = client._event_to_message(event)
    assert msg.mentions_me is True


def test_event_to_message_no_mention():
    client = make_client()
    from nio import RoomMessageText
    event = make_event(body="nothing relevant here", cls=RoomMessageText)
    msg = client._event_to_message(event)
    assert msg.mentions_me is False


def test_event_to_message_self_mention_not_flagged():
    """Own messages should not set mentions_me even if body has own localpart."""
    client = make_client()
    from nio import RoomMessageText
    event = make_event(sender="@test:matrix.org", body="test test test", cls=RoomMessageText)
    msg = client._event_to_message(event)
    assert msg.mentions_me is False


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
    from nio import RoomMessagesResponse, RoomMessageText
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
    from nio import RoomMessagesResponse, RoomMessageText
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


# ------------------------------------------------------------------
# Redactions
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_redaction_marks_message_redacted():
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = [
        Message("$evt1", "@a:m.org", "original body", 1000)
    ]

    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock()
    event.redacts = "$evt1"

    await client._on_redaction(room, event)

    msg = client.messages["!r:m.org"][0]
    assert msg.body == "[redacted]"
    assert msg.msgtype == "m.redacted"


@pytest.mark.asyncio
async def test_on_redaction_unknown_event_id_is_noop():
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = [
        Message("$evt1", "@a:m.org", "original body", 1000)
    ]

    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock()
    event.redacts = "$nonexistent"

    await client._on_redaction(room, event)
    # original message unchanged
    assert client.messages["!r:m.org"][0].body == "original body"


# ------------------------------------------------------------------
# Message edits (m.replace)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_unknown_event_handles_edit():
    """_on_unknown_event still handles edits from truly unknown event types."""
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = [
        Message("$original", "@a:m.org", "old text", 1000)
    ]

    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock()
    event.type = "m.room.message"
    event.source = {
        "content": {
            "m.relates_to": {
                "rel_type": "m.replace",
                "event_id": "$original",
            },
            "m.new_content": {"body": "new text"},
        }
    }

    await client._on_unknown_event(room, event)

    msg = client.messages["!r:m.org"][0]
    assert "new text" in msg.body
    assert "[edited]" in msg.body


@pytest.mark.asyncio
async def test_on_room_message_handles_edit_via_relates_to():
    """Edits arriving as RoomMessageText with m.relates_to should update in-place."""
    client = make_client()
    from nio import RoomMessageText
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = [
        Message("$original", "@a:m.org", "old text", 1000)
    ]

    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock(spec=RoomMessageText)
    event.event_id = "$edit_evt"
    event.sender = "@a:m.org"
    event.body = "* new text"
    event.server_timestamp = 2000
    event.source = {
        "content": {
            "msgtype": "m.text",
            "body": "* new text",
            "m.relates_to": {
                "rel_type": "m.replace",
                "event_id": "$original",
            },
            "m.new_content": {"body": "new text"},
        }
    }

    await client._on_room_message(room, event)

    msgs = client.messages["!r:m.org"]
    # Edit must NOT add a new message
    assert len(msgs) == 1
    assert msgs[0].event_id == "$original"
    assert "new text" in msgs[0].body
    assert "[edited]" in msgs[0].body


@pytest.mark.asyncio
async def test_on_unknown_event_ignores_non_message():
    client = make_client()
    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock()
    event.type = "m.reaction"
    event.source = {}
    # Should not raise, noop
    await client._on_unknown_event(room, event)


@pytest.mark.asyncio
async def test_on_unknown_event_ignores_non_replace():
    client = make_client()
    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock()
    event.type = "m.room.message"
    event.source = {"content": {"m.relates_to": {"rel_type": "m.thread"}}}
    await client._on_unknown_event(room, event)


# ------------------------------------------------------------------
# join_room / leave_room
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_join_room_returns_room_id_on_success():
    client = make_client()
    from nio import JoinResponse
    with patch.object(client._client, "join", new_callable=AsyncMock) as mock_join:
        mock_join.return_value = MagicMock(spec=JoinResponse, room_id="!new:m.org")
        result = await client.join_room("#alias:m.org")
    assert result == "!new:m.org"


@pytest.mark.asyncio
async def test_join_room_returns_none_on_failure():
    client = make_client()
    with patch.object(client._client, "join", new_callable=AsyncMock) as mock_join:
        mock_join.return_value = object()  # not JoinResponse
        result = await client.join_room("#bad:m.org")
    assert result is None


@pytest.mark.asyncio
async def test_join_room_swallows_exceptions():
    client = make_client()
    with patch.object(
        client._client, "join", new_callable=AsyncMock, side_effect=Exception("net error")
    ):
        result = await client.join_room("#bad:m.org")
    assert result is None


@pytest.mark.asyncio
async def test_leave_room_swallows_exception():
    client = make_client()
    with patch.object(
        client._client, "room_leave", new_callable=AsyncMock, side_effect=Exception("net")
    ):
        result = await client.leave_room("!r:m.org")
    assert result is False


@pytest.mark.asyncio
async def test_leave_room_removes_from_state():
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = []
    # Mock a successful leave (response has transport_response attr)
    leave_resp = MagicMock(spec=["transport_response"])
    with patch.object(client._client, "room_leave", new_callable=AsyncMock) as mock_leave:
        mock_leave.return_value = leave_resp
        result = await client.leave_room("!r:m.org")
    assert result is True
    assert "!r:m.org" not in client.rooms
    assert "!r:m.org" not in client.messages


# ------------------------------------------------------------------
# search_messages
# ------------------------------------------------------------------

def test_search_messages_finds_by_body():
    client = make_client()
    client.messages["!r:m.org"] = [
        Message("$1", "@a:m.org", "hello world", 1000),
        Message("$2", "@b:m.org", "goodbye", 2000),
    ]
    results = client.search_messages("hello")
    assert len(results) == 1
    assert results[0][1].event_id == "$1"


def test_search_messages_finds_by_sender():
    client = make_client()
    client.messages["!r:m.org"] = [
        Message("$1", "@alice:m.org", "hi", 1000),
        Message("$2", "@bob:m.org", "hey", 2000),
    ]
    results = client.search_messages("alice")
    assert len(results) == 1
    assert results[0][1].sender == "@alice:m.org"


def test_search_messages_case_insensitive():
    client = make_client()
    client.messages["!r:m.org"] = [Message("$1", "@a:m.org", "Hello World", 1000)]
    assert len(client.search_messages("hello world")) == 1
    assert len(client.search_messages("HELLO")) == 1


def test_search_messages_across_all_rooms():
    client = make_client()
    client.messages["!r1:m.org"] = [Message("$1", "@a:m.org", "ping", 1000)]
    client.messages["!r2:m.org"] = [Message("$2", "@b:m.org", "ping pong", 2000)]
    results = client.search_messages("ping")
    assert len(results) == 2


def test_search_messages_restricted_to_room():
    client = make_client()
    client.messages["!r1:m.org"] = [Message("$1", "@a:m.org", "ping", 1000)]
    client.messages["!r2:m.org"] = [Message("$2", "@b:m.org", "ping pong", 2000)]
    results = client.search_messages("ping", room_id="!r1:m.org")
    assert len(results) == 1
    assert results[0][0] == "!r1:m.org"


def test_search_messages_empty_result():
    client = make_client()
    client.messages["!r:m.org"] = [Message("$1", "@a:m.org", "hello", 1000)]
    assert client.search_messages("zzznomatch") == []


def test_search_messages_sorted_by_timestamp():
    client = make_client()
    client.messages["!r:m.org"] = [
        Message("$2", "@a:m.org", "match", 2000),
        Message("$1", "@a:m.org", "match", 1000),
    ]
    results = client.search_messages("match")
    assert results[0][1].event_id == "$1"
    assert results[1][1].event_id == "$2"


# ------------------------------------------------------------------
# get_room_members
# ------------------------------------------------------------------

def test_get_room_members_returns_user_ids():
    client = make_client()
    nio_room = MagicMock()
    nio_room.users = {"@alice:m.org": MagicMock(), "@bob:m.org": MagicMock()}
    client._client.rooms = {"!r:m.org": nio_room}
    members = client.get_room_members("!r:m.org")
    assert set(members) == {"@alice:m.org", "@bob:m.org"}


def test_get_room_members_unknown_room():
    client = make_client()
    client._client.rooms = {}
    assert client.get_room_members("!unknown:m.org") == []


# ------------------------------------------------------------------
# start_sync + login paths
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_raises_on_error():
    client = make_client()
    with patch.object(client._client, "login", new_callable=AsyncMock) as mock_login:
        mock_login.return_value = object()  # not LoginResponse
        with pytest.raises(RuntimeError, match="Login failed"):
            await client.login("badpassword")


@pytest.mark.asyncio
async def test_start_sync_calls_sync_and_starts_task():
    client = make_client()
    from nio import SyncResponse
    mock_resp = MagicMock(spec=SyncResponse)
    with patch.object(client._client, "sync", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = mock_resp
        client._client.rooms = {}
        await client.start_sync()
    assert client._running is True
    assert client._sync_task is not None
    client._sync_task.cancel()  # cleanup


@pytest.mark.asyncio
async def test_login_succeeds_sets_no_error():
    """Verify successful login calls nio login and doesn't raise."""
    client = make_client()
    from nio import LoginResponse
    mock_resp = MagicMock(spec=LoginResponse)
    with patch.object(client._client, "login", new_callable=AsyncMock) as mock_login:
        mock_login.return_value = mock_resp
        await client.login("validpw")  # should not raise
    mock_login.assert_called_once_with("validpw", device_name="matrixtui")


@pytest.mark.asyncio
async def test_logout_with_token_calls_logout():
    client = make_client()
    client._client.access_token = "tok123"
    client._client.logout = AsyncMock()
    client._client.close = AsyncMock()
    await client.logout()
    client._client.logout.assert_called_once()
    client._client.close.assert_called_once()


@pytest.mark.asyncio
async def test_logout_swallows_logout_exception():
    """If nio logout raises, we still close the session."""
    client = make_client()
    client._client.access_token = "tok123"
    client._client.logout = AsyncMock(side_effect=Exception("server error"))
    client._client.close = AsyncMock()
    await client.logout()  # should not raise
    client._client.close.assert_called_once()


@pytest.mark.asyncio
async def test_on_room_name_noop_for_unknown_room():
    """_on_room_name should be silent when the room isn't in self.rooms."""
    client = make_client()
    room = MagicMock()
    room.room_id = "!unknown:m.org"
    event = MagicMock()
    cb = MagicMock()
    client.on_room_update(cb)
    await client._on_room_name(room, event)
    cb.assert_not_called()


@pytest.mark.asyncio
async def test_on_room_name_updates_display_name():
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Old")
    room = MagicMock()
    room.room_id = "!r:m.org"
    room.display_name = "New Name"
    room.name = None
    room.users = {}
    room.own_user_id = "@me:m.org"
    event = MagicMock()
    await client._on_room_name(room, event)
    assert client.rooms["!r:m.org"].display_name == "New Name"


def test_nio_client_property():
    client = make_client()
    assert client.nio_client is client._client


def test_client_has_invites_dict():
    client = make_client()
    assert client.invites == {}


# ------------------------------------------------------------------
# Invite events
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_invite_event_stores_invite():
    client = make_client()
    cb = MagicMock()
    client.on_invite(cb)

    room = MagicMock()
    room.room_id = "!invited:m.org"

    event = MagicMock()
    event.membership = "invite"
    event.state_key = "@test:matrix.org"  # targets this user
    event.sender = "@alice:m.org"

    await client._on_invite_event(room, event)

    assert client.invites["!invited:m.org"] == "@alice:m.org"
    cb.assert_called_once_with("!invited:m.org", "@alice:m.org")


@pytest.mark.asyncio
async def test_on_invite_event_ignores_other_targets():
    """Invites targeting a different user should be ignored."""
    client = make_client()
    cb = MagicMock()
    client.on_invite(cb)

    room = MagicMock()
    room.room_id = "!invited:m.org"
    event = MagicMock()
    event.membership = "invite"
    event.state_key = "@other:m.org"  # not this user
    event.sender = "@alice:m.org"

    await client._on_invite_event(room, event)

    assert "!invited:m.org" not in client.invites
    cb.assert_not_called()


@pytest.mark.asyncio
async def test_on_invite_event_ignores_non_invite():
    """Non-invite membership events should be ignored."""
    client = make_client()
    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock()
    event.membership = "join"
    event.state_key = "@test:matrix.org"
    event.sender = "@alice:m.org"

    await client._on_invite_event(room, event)
    assert "!r:m.org" not in client.invites


# ------------------------------------------------------------------
# get_room_topic
# ------------------------------------------------------------------

def test_get_room_topic_returns_topic():
    client = make_client()
    nio_room = MagicMock()
    nio_room.topic = "Welcome to the room!"
    client._client.rooms = {"!r:m.org": nio_room}
    assert client.get_room_topic("!r:m.org") == "Welcome to the room!"


def test_get_room_topic_returns_none_when_unset():
    client = make_client()
    nio_room = MagicMock()
    nio_room.topic = None
    client._client.rooms = {"!r:m.org": nio_room}
    assert client.get_room_topic("!r:m.org") is None


def test_get_room_topic_returns_none_for_unknown_room():
    client = make_client()
    client._client.rooms = {}
    assert client.get_room_topic("!unknown:m.org") is None


# ------------------------------------------------------------------
# set_display_name
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_display_name_returns_true_on_success():
    client = make_client()
    from nio import ProfileSetDisplayNameResponse
    with patch.object(
        client._client, "set_displayname", new_callable=AsyncMock
    ) as mock_set:
        mock_set.return_value = MagicMock(spec=ProfileSetDisplayNameResponse)
        result = await client.set_display_name("Alice")
    assert result is True
    mock_set.assert_called_once_with("Alice")


@pytest.mark.asyncio
async def test_set_display_name_returns_false_on_failure():
    client = make_client()
    with patch.object(
        client._client, "set_displayname", new_callable=AsyncMock
    ) as mock_set:
        mock_set.return_value = object()  # not ProfileSetDisplayNameResponse
        result = await client.set_display_name("Alice")
    assert result is False


@pytest.mark.asyncio
async def test_set_display_name_swallows_exception():
    client = make_client()
    with patch.object(
        client._client, "set_displayname", new_callable=AsyncMock,
        side_effect=Exception("net error")
    ):
        result = await client.set_display_name("Alice")
    assert result is False


# ------------------------------------------------------------------
# restore_session (sync)
# ------------------------------------------------------------------

def test_restore_session_sets_token_and_device():
    client = make_client()
    client.restore_session("tok_abc", "DEV1")
    assert client._client.access_token == "tok_abc"
    assert client._client.device_id == "DEV1"


# ------------------------------------------------------------------
# room_update callback coverage: message/redaction/unknown paths
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_room_message_fires_room_update_callback():
    """room_update callback must fire on new message (line 212)."""
    client = make_client()
    from nio import RoomMessageText
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = []
    ru_cb = MagicMock()
    client.on_room_update(ru_cb)

    room = MagicMock()
    room.room_id = "!r:m.org"
    event = make_event(cls=RoomMessageText)
    await client._on_room_message(room, event)

    ru_cb.assert_called_with("!r:m.org")


@pytest.mark.asyncio
async def test_on_room_message_edit_fires_room_update_callback():
    """room_update callback must fire on edit path (line 197)."""
    client = make_client()
    from nio import RoomMessageText
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = [Message("$orig", "@a:m.org", "old", 1000)]
    ru_cb = MagicMock()
    client.on_room_update(ru_cb)

    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock(spec=RoomMessageText)
    event.event_id = "$edit"
    event.sender = "@a:m.org"
    event.body = "* new"
    event.server_timestamp = 2000
    event.source = {
        "content": {
            "m.relates_to": {"rel_type": "m.replace", "event_id": "$orig"},
            "m.new_content": {"body": "new"},
        }
    }
    await client._on_room_message(room, event)
    ru_cb.assert_called_with("!r:m.org")


@pytest.mark.asyncio
async def test_on_redaction_fires_room_update_callback():
    """room_update callback must fire after redaction (line 235)."""
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = [Message("$e", "@a:m.org", "body", 1000)]
    ru_cb = MagicMock()
    client.on_room_update(ru_cb)

    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock()
    event.redacts = "$e"
    await client._on_redaction(room, event)
    ru_cb.assert_called_with("!r:m.org")


@pytest.mark.asyncio
async def test_on_unknown_event_edit_fires_room_update_callback():
    """room_update callback must fire in _on_unknown_event edit path (line 254)."""
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Room")
    client.messages["!r:m.org"] = [Message("$orig", "@a:m.org", "old", 1000)]
    ru_cb = MagicMock()
    client.on_room_update(ru_cb)

    room = MagicMock()
    room.room_id = "!r:m.org"
    event = MagicMock()
    event.type = "m.room.message"
    event.source = {
        "content": {
            "m.relates_to": {"rel_type": "m.replace", "event_id": "$orig"},
            "m.new_content": {"body": "updated"},
        }
    }
    await client._on_unknown_event(room, event)
    ru_cb.assert_called_with("!r:m.org")


# ------------------------------------------------------------------
# _sync_loop error recovery
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_loop_recovers_from_exception():
    """_sync_loop logs errors and continues (lines 152-154)."""
    client = make_client()
    call_count = 0

    async def failing_then_stop(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient error")
        # Stop the loop after second call
        client._running = False
        from nio import SyncResponse
        return MagicMock(spec=SyncResponse)

    client._client.sync = failing_then_stop
    client._client.rooms = {}
    client._running = True

    with patch("matrixtui.client.asyncio.sleep", new_callable=AsyncMock):
        await client._sync_loop()

    assert call_count == 2  # ran twice: first failed, second stopped loop


@pytest.mark.asyncio
async def test_sync_loop_breaks_on_cancelled():
    """_sync_loop exits cleanly on CancelledError (line 151)."""
    import asyncio
    client = make_client()

    async def cancel_immediately(*args, **kwargs):
        raise asyncio.CancelledError()

    client._client.sync = cancel_immediately
    client._running = True
    await client._sync_loop()  # should return without raising
    # If we get here, the break worked correctly


@pytest.mark.asyncio
async def test_on_room_name_fires_room_update_callback():
    """room_update callback fires when room name changes (line 219)."""
    client = make_client()
    client.rooms["!r:m.org"] = RoomSummary("!r:m.org", "Old")
    ru_cb = MagicMock()
    client.on_room_update(ru_cb)

    room = MagicMock()
    room.room_id = "!r:m.org"
    room.display_name = "New Name"
    room.name = None
    room.users = {}
    room.own_user_id = "@me:m.org"
    event = MagicMock()
    await client._on_room_name(room, event)

    ru_cb.assert_called_once_with("!r:m.org")
