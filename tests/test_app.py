"""Unit tests for MatrixApp TUI using Textual's run_test pilot."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matrixtui.app import (
    InviteReceived,
    MatrixApp,
    NewMessage,
    RoomListItem,
    RoomUpdated,
    TypingUpdated,
)
from matrixtui.client import MatrixClient, Message, RoomSummary


def make_client_with_rooms():
    with patch("matrixtui.client.AsyncClient"):
        client = MatrixClient("https://matrix.org", "@test:matrix.org")
    client.rooms = {
        "!r1:m.org": RoomSummary("!r1:m.org", "Room One", unread_count=2, last_ts=2000,
                                  member_count=5),
        "!r2:m.org": RoomSummary("!r2:m.org", "Room Two", unread_count=0, last_ts=1000,
                                  member_count=3),
    }
    client.messages = {
        "!r1:m.org": [
            Message("$1", "@alice:m.org", "hello world", 1699000000000),
            Message("$2", "@test:matrix.org", "hi there", 1699000010000, is_me=True),
        ],
        "!r2:m.org": [
            Message("$3", "@bob:m.org", "hey test, ping?", 1699000020000, mentions_me=True),
        ],
    }
    # Provide empty nio rooms for get_room_members / get_room_topic
    client._client.rooms = {
        "!r1:m.org": MagicMock(users={}, topic="Welcome!"),
        "!r2:m.org": MagicMock(users={}, topic=None),
    }
    return client


def make_app(client=None):
    client = client or make_client_with_rooms()
    app = MatrixApp(client)

    async def fake_connect():
        app.query_one("#status-bar").update("Connected as @test:matrix.org")
        app._rebuild_room_list()

    app._connect = fake_connect
    return app, client


def _static_text(widget) -> str:
    """Get rendered text from a Static widget."""
    return str(widget.content)


# ------------------------------------------------------------------
# RoomListItem (pure logic, no pilot needed)
# ------------------------------------------------------------------

def test_room_list_item_text_with_unread():
    summary = RoomSummary("!r:m.org", "My Room", unread_count=5)
    item = RoomListItem(summary)
    assert "[5]" in item._text()
    assert "My Room" in item._text()


def test_room_list_item_text_no_unread():
    summary = RoomSummary("!r:m.org", "My Room", unread_count=0)
    item = RoomListItem(summary)
    assert "[" not in item._text()


def test_room_list_item_truncates_long_name():
    summary = RoomSummary("!r:m.org", "A" * 30)
    item = RoomListItem(summary)
    assert len(item._text()) <= 30


def test_room_list_item_uses_room_id_when_no_name():
    summary = RoomSummary("!r:m.org", "")
    item = RoomListItem(summary)
    assert "!r:m.org" in item._text()


def test_room_list_item_refresh_text():
    summary = RoomSummary("!r:m.org", "Room", unread_count=0)
    item = RoomListItem(summary)
    assert "[3]" not in item._text()
    summary.unread_count = 3
    item.refresh_text()
    # The Label was updated (internal state reflects new count)
    assert "[3]" in item._text()


# ------------------------------------------------------------------
# TMessage subclasses (pure logic)
# ------------------------------------------------------------------

def test_room_updated_message():
    msg = RoomUpdated("!r:m.org")
    assert msg.room_id == "!r:m.org"


def test_new_message_message():
    m = Message("$1", "@a:m.org", "hi", 1000)
    msg = NewMessage("!r:m.org", m)
    assert msg.room_id == "!r:m.org"
    assert msg.msg is m


def test_typing_updated_message():
    msg = TypingUpdated("!r:m.org", ["@alice:m.org"])
    assert msg.room_id == "!r:m.org"
    assert msg.users == ["@alice:m.org"]


def test_invite_received_message():
    msg = InviteReceived("!r:m.org", "@alice:m.org")
    assert msg.room_id == "!r:m.org"
    assert msg.inviter == "@alice:m.org"


# ------------------------------------------------------------------
# App startup
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_welcome_message_shown_on_mount():
    """Welcome/hint text is shown in the log pane before any room is selected."""
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        # Should have the welcome content visible immediately
        assert log.lines


@pytest.mark.asyncio
async def test_app_renders_room_list():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        assert len(app._room_items) == 2
        assert "!r1:m.org" in app._room_items
        assert "!r2:m.org" in app._room_items


@pytest.mark.asyncio
async def test_app_room_list_sorted_by_last_ts():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        children = list(lv.query(RoomListItem))
        assert children[0]._room_id == "!r1:m.org"
        assert children[1]._room_id == "!r2:m.org"


@pytest.mark.asyncio
async def test_app_status_bar_shows_connected():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import Static
        status = app.query_one("#status-bar", Static)
        assert "Connected" in _static_text(status)


# ------------------------------------------------------------------
# Room selection
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_select_room_sets_current_room():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert app.current_room == "!r1:m.org"


@pytest.mark.asyncio
async def test_select_room_updates_title():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView, Static
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause(0.2)
        title = _static_text(app.query_one("#room-title", Static))
        assert "Room One" in title


@pytest.mark.asyncio
async def test_select_room_shows_messages():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView, RichLog
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause(0.2)
        log = app.query_one("#messages", RichLog)
        # RichLog should have lines (not empty)
        assert log.lines  # internal buffer has content


# ------------------------------------------------------------------
# Room filter
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_room_filter_hides_non_matching():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import Input
        filter_input = app.query_one("#room-filter-input", Input)
        filter_input.focus()
        # Type "one" by pressing keys
        await pilot.press("o", "n", "e")
        await pilot.pause(0.2)
        assert app._room_items["!r1:m.org"].display is True
        assert app._room_items["!r2:m.org"].display is False


@pytest.mark.asyncio
async def test_room_filter_empty_shows_all():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import Input
        fi = app.query_one("#room-filter-input", Input)
        fi.focus()
        await pilot.press("o", "n", "e")
        await pilot.pause(0.1)
        # Clear by deleting characters
        await pilot.press("backspace", "backspace", "backspace")
        await pilot.pause(0.2)
        # Both rooms should be visible
        assert app._room_items["!r1:m.org"].display is not False
        assert app._room_items["!r2:m.org"].display is not False


# ------------------------------------------------------------------
# Keyboard bindings
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ctrl_f_focuses_filter():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+f")
        await pilot.pause(0.1)
        from textual.widgets import Input
        assert app.query_one("#room-filter-input", Input).has_focus


@pytest.mark.asyncio
async def test_escape_focuses_message_input():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+f")
        await pilot.pause(0.1)
        await pilot.press("escape")
        await pilot.pause(0.1)
        from textual.widgets import Input
        assert app.query_one("#msg-input", Input).has_focus


# ------------------------------------------------------------------
# Slash commands (send via Input.insert_text_at_cursor + enter)
# ------------------------------------------------------------------

async def _send_command(pilot, app, text: str) -> None:
    """Helper: type a command into msg-input and submit."""
    from textual.widgets import Input
    inp = app.query_one("#msg-input", Input)
    inp.focus()
    inp.insert_text_at_cursor(text)
    await pilot.press("enter")
    await pilot.pause(0.2)


@pytest.mark.asyncio
async def test_help_command_writes_to_log():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/help")
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        assert log.lines  # has content


@pytest.mark.asyncio
async def test_members_command_no_room_is_noop():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        # No room selected
        await _send_command(pilot, app, "/members")
        assert app.current_room is None  # didn't crash


@pytest.mark.asyncio
async def test_members_command_with_room():
    app, client = make_app()
    client._client.rooms["!r1:m.org"].users = {
        "@alice:m.org": MagicMock(),
        "@bob:m.org": MagicMock(),
    }
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        # Select room 1
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        await _send_command(pilot, app, "/members")
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        assert log.lines


@pytest.mark.asyncio
async def test_topic_command_shows_topic():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        await _send_command(pilot, app, "/topic")
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        assert log.lines  # "Welcome!" or similar


@pytest.mark.asyncio
async def test_topic_command_no_room_is_noop():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/topic")
        # No room selected → noop, no crash


@pytest.mark.asyncio
async def test_search_command_with_results():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        await _send_command(pilot, app, "/search hello")
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        assert log.lines


@pytest.mark.asyncio
async def test_search_command_no_results():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        await _send_command(pilot, app, "/search zzznomatch")
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        assert log.lines  # shows "No results" message


@pytest.mark.asyncio
async def test_nick_command_calls_set_display_name():
    app, client = make_app()
    client.set_display_name = AsyncMock(return_value=True)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/nick NewName")
        await pilot.pause(0.1)
        client.set_display_name.assert_called_once_with("NewName")


@pytest.mark.asyncio
async def test_nick_command_empty_is_noop():
    app, client = make_app()
    client.set_display_name = AsyncMock(return_value=True)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/nick ")
        # Empty name → noop
        client.set_display_name.assert_not_called()


# ------------------------------------------------------------------
# Typing indicator
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_typing_indicator_shown_in_active_room():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        app.post_message(TypingUpdated("!r1:m.org", ["@alice:m.org"]))
        await pilot.pause(0.2)
        from textual.widgets import Static
        indicator = app.query_one("#typing-indicator", Static)
        assert "alice" in _static_text(indicator)


@pytest.mark.asyncio
async def test_typing_indicator_clears():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        app.post_message(TypingUpdated("!r1:m.org", ["@alice:m.org"]))
        await pilot.pause(0.1)
        app.post_message(TypingUpdated("!r1:m.org", []))
        await pilot.pause(0.2)
        from textual.widgets import Static
        indicator = app.query_one("#typing-indicator", Static)
        assert _static_text(indicator).strip() == ""


@pytest.mark.asyncio
async def test_typing_indicator_ignored_for_other_room():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        app.post_message(TypingUpdated("!r2:m.org", ["@alice:m.org"]))
        await pilot.pause(0.2)
        from textual.widgets import Static
        indicator = app.query_one("#typing-indicator", Static)
        assert "alice" not in _static_text(indicator)


# ------------------------------------------------------------------
# Invite notification
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invite_shown_in_status_bar():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        app.post_message(InviteReceived("!new:m.org", "@alice:m.org"))
        await pilot.pause(0.2)
        from textual.widgets import Static
        status = app.query_one("#status-bar", Static)
        text = _static_text(status)
        assert "alice" in text
        assert "/join" in text


# ------------------------------------------------------------------
# NewMessage: refreshes room item and appends to log when room active
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_message_refreshes_room_item_text():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        client.rooms["!r1:m.org"].unread_count = 7
        new_msg = Message("$99", "@alice:m.org", "new msg", 3000)
        app.post_message(NewMessage("!r1:m.org", new_msg))
        await pilot.pause(0.2)
        assert "[7]" in app._room_items["!r1:m.org"]._text()


@pytest.mark.asyncio
async def test_new_message_appends_to_log_when_room_active():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        initial_lines = len(log.lines)
        new_msg = Message("$live", "@alice:m.org", "live message", 1699999999000)
        app.post_message(NewMessage("!r1:m.org", new_msg))
        await pilot.pause(0.2)
        assert len(log.lines) > initial_lines


# ------------------------------------------------------------------
# Schedule callbacks (bridge methods)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_methods_dont_crash():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        msg = Message("$x", "@a:m.org", "test", 1000)
        app._schedule_room_update("!r1:m.org")
        app._schedule_new_message("!r1:m.org", msg)
        app._schedule_typing_update("!r1:m.org", ["@alice:m.org"])
        app._schedule_invite("!r:m.org", "@alice:m.org")
        await pilot.pause(0.2)
        # No assertion needed — no crash means these work


# ------------------------------------------------------------------
# Filter input: enter key focuses room list
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filter_enter_focuses_room_list():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import Input, ListView
        fi = app.query_one("#room-filter-input", Input)
        fi.focus()
        await pilot.press("enter")
        await pilot.pause(0.1)
        lv = app.query_one("#room-list", ListView)
        assert lv.has_focus


# ------------------------------------------------------------------
# Empty input submission is a noop
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_input_is_noop():
    app, client = make_app()
    client.send_message = AsyncMock(return_value="$x")
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import Input
        inp = app.query_one("#msg-input", Input)
        inp.focus()
        await pilot.press("enter")  # submit empty
        await pilot.pause(0.1)
        client.send_message.assert_not_called()


# ------------------------------------------------------------------
# Send plain message
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_plain_message():
    app, client = make_app()
    client.send_message = AsyncMock(return_value="$sent")
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        # Select a room
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        await _send_command(pilot, app, "Hello, world!")
        client.send_message.assert_called_once_with("!r1:m.org", "Hello, world!")


# ------------------------------------------------------------------
# /join command
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_join_command_success():
    app, client = make_app()
    client.join_room = AsyncMock(return_value="!new:m.org")
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/join #new:m.org")
        await pilot.pause(0.2)
        client.join_room.assert_called_once_with("#new:m.org")
        from textual.widgets import Static
        status = app.query_one("#status-bar", Static)
        assert "Joined" in _static_text(status)


@pytest.mark.asyncio
async def test_join_command_failure():
    app, client = make_app()
    client.join_room = AsyncMock(return_value=None)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/join #bad:m.org")
        await pilot.pause(0.2)
        from textual.widgets import Static
        status = app.query_one("#status-bar", Static)
        assert "Failed" in _static_text(status)


# ------------------------------------------------------------------
# /leave command
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_leave_command_success():
    app, client = make_app()
    client.leave_room = AsyncMock(return_value=True)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        assert app.current_room == "!r1:m.org"
        await _send_command(pilot, app, "/leave")
        await pilot.pause(0.2)
        client.leave_room.assert_called_once_with("!r1:m.org")
        assert app.current_room is None
        from textual.widgets import Static
        status = app.query_one("#status-bar", Static)
        assert "Left" in _static_text(status)


@pytest.mark.asyncio
async def test_leave_command_failure():
    app, client = make_app()
    client.leave_room = AsyncMock(return_value=False)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        await _send_command(pilot, app, "/leave")
        await pilot.pause(0.2)
        from textual.widgets import Static
        status = app.query_one("#status-bar", Static)
        assert "Failed" in _static_text(status)


@pytest.mark.asyncio
async def test_leave_command_no_room_is_noop():
    app, client = make_app()
    client.leave_room = AsyncMock()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/leave")
        await pilot.pause(0.1)
        client.leave_room.assert_not_called()


# ------------------------------------------------------------------
# /topic no-topic branch
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_topic_command_no_topic_set():
    app, client = make_app()
    # room 2 has topic=None
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        # Navigate to room 2 (second item)
        await pilot.press("down", "down", "enter")
        await pilot.pause(0.1)
        await _send_command(pilot, app, "/topic")
        await pilot.pause(0.2)
        from textual.widgets import RichLog
        assert app.query_one("#messages", RichLog).lines


# ------------------------------------------------------------------
# /nick failure path
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nick_command_failure():
    app, client = make_app()
    client.set_display_name = AsyncMock(return_value=False)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/nick NewName")
        await pilot.pause(0.2)
        from textual.widgets import Static
        status = app.query_one("#status-bar", Static)
        assert "Failed" in _static_text(status)


# ------------------------------------------------------------------
# Mention highlight (_append_message branch)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mention_highlighted_in_log():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "down", "enter")
        await pilot.pause(0.2)
        # Room Two has a mention message; the log should have content
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        assert log.lines  # mention message was rendered


# ------------------------------------------------------------------
# action_reload_history (Ctrl+R)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ctrl_r_reloads_history():
    app, client = make_app()
    client.load_history = AsyncMock(return_value=[])
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        await pilot.press("ctrl+r")
        await pilot.pause(0.2)
        client.load_history.assert_called_once_with("!r1:m.org")


@pytest.mark.asyncio
async def test_ctrl_r_noop_when_no_room():
    app, client = make_app()
    client.load_history = AsyncMock(return_value=[])
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+r")
        await pilot.pause(0.1)
        client.load_history.assert_not_called()


# ------------------------------------------------------------------
# _connect error path
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_error_shown_in_status_bar():
    """If _connect() login raises, the except branch updates the status bar."""
    with patch("matrixtui.client.AsyncClient"):
        client = MatrixClient("https://matrix.org", "@test:matrix.org")
    client.login = AsyncMock(side_effect=RuntimeError("bad credentials"))
    client.logout = AsyncMock()
    client._client.close = AsyncMock()

    app = MatrixApp(client)

    import os
    env = {
        "MATRIX_HOMESERVER": "https://matrix.org",
        "MATRIX_USER": "@test:matrix.org",
        "MATRIX_PASSWORD": "pw",
    }
    with patch.dict(os.environ, env):
        with patch("matrixtui.app.Config.from_env") as mock_cfg:
            mock_cfg.return_value.password = "pw"
            async with app.run_test(size=(120, 35)) as pilot:
                await pilot.pause(0.5)
                from textual.widgets import Static
                status = app.query_one("#status-bar", Static)
                assert "Error" in _static_text(status)
                assert "bad credentials" in _static_text(status)


@pytest.mark.asyncio
async def test_connect_uses_real_login_path():
    """_connect() calls client.login() and start_sync(), then rebuild list."""
    with patch("matrixtui.client.AsyncClient"):
        client = MatrixClient("https://matrix.org", "@test:matrix.org")
    client.login = AsyncMock()
    client.start_sync = AsyncMock()
    client.logout = AsyncMock()
    client._client.close = AsyncMock()
    client.rooms = {
        "!r1:m.org": RoomSummary("!r1:m.org", "Room", last_ts=1000, member_count=2),
    }
    client.messages = {"!r1:m.org": []}
    client._client.rooms = {"!r1:m.org": MagicMock(users={}, topic=None)}

    app = MatrixApp(client)
    # Do NOT override _connect — use the real one

    import os
    env = {
        "MATRIX_HOMESERVER": "https://matrix.org",
        "MATRIX_USER": "@test:matrix.org",
        "MATRIX_PASSWORD": "pw",
    }
    with patch.dict(os.environ, env):
        with patch("matrixtui.app.Config.from_env") as mock_cfg:
            mock_cfg.return_value.password = "pw"
            async with app.run_test(size=(120, 35)) as pilot:
                await pilot.pause(0.5)

    client.login.assert_called_once_with("pw")
    client.start_sync.assert_called_once()


# ------------------------------------------------------------------
# action_quit
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_quit_calls_logout():
    app, client = make_app()
    client.logout = AsyncMock()
    client._client.close = AsyncMock()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await app.action_quit()
    client.logout.assert_called_once()


# ------------------------------------------------------------------
# /me emote command
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_me_command_sends_emote():
    app, client = make_app()
    client.send_emote = AsyncMock(return_value="$emote1")
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        await _send_command(pilot, app, "/me waves hello")
        client.send_emote.assert_called_once_with("!r1:m.org", "waves hello")


@pytest.mark.asyncio
async def test_me_command_no_room_is_noop():
    app, client = make_app()
    client.send_emote = AsyncMock()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/me waves")
        client.send_emote.assert_not_called()


@pytest.mark.asyncio
async def test_me_command_empty_is_noop():
    app, client = make_app()
    client.send_emote = AsyncMock()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        # Call handler directly with empty emote
        import asyncio
        await asyncio.ensure_future(app._handle_me(""))
        await pilot.pause(0.1)
        client.send_emote.assert_not_called()


# ------------------------------------------------------------------
# Unread badge clears on room select
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unread_badge_clears_on_room_select():
    app, client = make_app()
    client.rooms["!r1:m.org"].unread_count = 5
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        # Verify badge shows before selecting
        assert "[5]" in app._room_items["!r1:m.org"]._text()
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.2)
        # Badge should be gone after selecting
        assert "[5]" not in app._room_items["!r1:m.org"]._text()
        assert client.rooms["!r1:m.org"].unread_count == 0


# ------------------------------------------------------------------
# Date separators in message pane
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whois_command_shows_profile():
    app, client = make_app()
    client.get_user_profile = AsyncMock(return_value={
        "display_name": "Alice Smith",
        "avatar_url": "mxc://matrix.org/xyz",
    })
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/whois @alice:m.org")
        await pilot.pause(0.2)
        from textual.widgets import RichLog
        assert app.query_one("#messages", RichLog).lines


@pytest.mark.asyncio
async def test_whois_command_no_profile():
    app, client = make_app()
    client.get_user_profile = AsyncMock(return_value=None)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        await _send_command(pilot, app, "/whois @unknown:m.org")
        await pilot.pause(0.2)
        from textual.widgets import RichLog
        assert app.query_one("#messages", RichLog).lines  # shows error message


@pytest.mark.asyncio
async def test_clear_command():
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        assert len(log.lines) > 0  # welcome message present
        await _send_command(pilot, app, "/clear")
        await pilot.pause(0.1)
        assert len(log.lines) == 0


@pytest.mark.asyncio
async def test_status_bar_shows_unread_count():
    app, client = make_app()
    client.rooms["!r1:m.org"].unread_count = 5
    client.rooms["!r2:m.org"].unread_count = 3
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        # Trigger a room update to fire _update_status
        from matrixtui.app import RoomUpdated
        app.post_message(RoomUpdated("!r1:m.org"))
        await pilot.pause(0.2)
        from textual.widgets import Static
        status = _static_text(app.query_one("#status-bar", Static))
        assert "unread" in status


@pytest.mark.asyncio
async def test_date_separator_shown_between_days():
    app, client = make_app()
    # Add messages on two different days
    client.messages["!r1:m.org"] = [
        Message("$a", "@alice:m.org", "day one message", 1699000000000),   # 2023-11-03
        Message("$b", "@bob:m.org",   "day two message", 1699100000000),   # 2023-11-04
    ]
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.2)
        from textual.widgets import RichLog
        log = app.query_one("#messages", RichLog)
        # Should have date separator lines (more lines than just 2 messages)
        assert len(log.lines) > 2


# ------------------------------------------------------------------
# Edge-case guard clauses
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_empty_query_is_noop():
    """_handle_search('') returns early without writing to log."""
    app, client = make_app()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        from textual.widgets import ListView, RichLog
        lv = app.query_one("#room-list", ListView)
        lv.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        log = app.query_one("#messages", RichLog)
        log.clear()
        # Directly invoke with empty query
        app._handle_search("")
        await pilot.pause(0.1)
        # Log should still be empty (early return hit)
        assert not log.lines


@pytest.mark.asyncio
async def test_nick_empty_via_handler():
    """_handle_nick('') returns early — covers the guard clause."""
    app, client = make_app()
    client.set_display_name = AsyncMock(return_value=True)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause(0.3)
        import asyncio
        # Call handler directly with empty string
        await asyncio.ensure_future(app._handle_nick(""))
        await pilot.pause(0.1)
        client.set_display_name.assert_not_called()
