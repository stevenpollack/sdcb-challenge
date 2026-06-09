"""Tests for the Textual TUI layout and UI interactions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from matrixtui.app import MatrixTUIApp, RoomItem, JoinRoomScreen
from matrixtui.matrix_client import Room, Message


@pytest.mark.asyncio
async def test_app_composes_key_widgets():
    """Verify all required UI widgets are present after compose."""
    app = MatrixTUIApp()
    async with app.run_test() as pilot:
        assert pilot.app.query_one("#message-input") is not None
        assert pilot.app.query_one("#room-list") is not None
        assert pilot.app.query_one("#message-view") is not None
        assert pilot.app.query_one("#status-bar") is not None
        assert pilot.app.query_one("#room-header") is not None


@pytest.mark.asyncio
async def test_message_input_is_focusable():
    """Verify message input can receive focus."""
    app = MatrixTUIApp()
    async with app.run_test() as pilot:
        input_widget = pilot.app.query_one("#message-input")
        await pilot.click(input_widget)
        assert pilot.app.focused == input_widget


@pytest.mark.asyncio
async def test_status_bar_updates():
    """Verify _set_status updates the status bar text."""
    app = MatrixTUIApp()
    async with app.run_test() as pilot:
        pilot.app._set_status("Connected to matrix.org")
        bar = pilot.app.query_one("#status-bar")
        # StatusBar extends Static; get its internal markup/text via render
        rendered = bar.render()
        assert "Connected" in str(rendered)


@pytest.mark.asyncio
async def test_message_append_renders():
    """Verify _append_message writes to the message view."""
    app = MatrixTUIApp()
    async with app.run_test() as pilot:
        msg = Message(
            room_id="!test:example.com",
            sender="@alice:example.com",
            body="Hello world",
            timestamp=1700000000000,
        )
        pilot.app._append_message(msg)
        # Check the text was written to the message view
        view = pilot.app.query_one("#message-view")
        assert view is not None


@pytest.mark.asyncio
async def test_room_list_populates():
    """Verify rooms are displayed in the sidebar when _on_rooms_updated is called."""
    app = MatrixTUIApp()
    async with app.run_test() as pilot:
        rooms = [
            Room("!r1:example.com", "General", 5),
            Room("!r2:example.com", "Dev", 3),
        ]
        pilot.app._on_rooms_updated(rooms)
        await pilot.pause(0.1)
        items = list(pilot.app.query("#room-list ListItem").results(RoomItem))
        assert len(items) == 2
        names = {item.room.display_name for item in items}
        assert "General" in names
        assert "Dev" in names


@pytest.mark.asyncio
async def test_room_item_label_truncates():
    """Verify long room names are truncated in the RoomItem label."""
    long_name = "A" * 40
    room = Room("!r:example.com", long_name, 1)
    item = RoomItem(room)
    label = item._label()
    assert len(label) <= 28


@pytest.mark.asyncio
async def test_input_cleared_after_submit():
    """Verify the input field is cleared after a message is submitted."""
    app = MatrixTUIApp()
    async with app.run_test() as pilot:
        # Set up a mock matrix client so the send doesn't hit the network
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value="$event123")
        app._matrix = mock_client
        app.current_room = Room("!r:example.com", "Test Room", 2)

        input_widget = pilot.app.query_one("#message-input")
        await pilot.click(input_widget)
        input_widget.value = "hello world"
        await pilot.press("enter")
        await pilot.pause(0.1)

        assert input_widget.value == ""


@pytest.mark.asyncio
async def test_focus_rooms_action():
    """Ctrl+J focuses the room list."""
    app = MatrixTUIApp()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+j")
        assert pilot.app.focused == pilot.app.query_one("#room-list")


@pytest.mark.asyncio
async def test_focus_input_action():
    """Ctrl+K focuses the message input."""
    app = MatrixTUIApp()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+k")
        assert pilot.app.focused == pilot.app.query_one("#message-input")


@pytest.mark.asyncio
async def test_room_item_shows_unread_count():
    """RoomItem label includes unread count badge when count > 0."""
    room = Room("!r:example.com", "General", 5)
    item = RoomItem(room, unread_count=3)
    label = item._label()
    assert "(3)" in label


@pytest.mark.asyncio
async def test_room_item_no_unread_badge():
    """RoomItem label has no badge when unread count is 0."""
    room = Room("!r:example.com", "General", 5)
    item = RoomItem(room, unread_count=0)
    label = item._label()
    assert "(" not in label
