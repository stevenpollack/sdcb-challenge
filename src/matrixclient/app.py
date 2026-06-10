"""Textual TUI application for Matrix."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message as TxtMessage
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from .client import MatrixClient, Message, Room
from .config import AppConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom messages (Textual inter-widget messaging)
# ---------------------------------------------------------------------------


class RoomSelected(TxtMessage):
    def __init__(self, room_id: str) -> None:
        super().__init__()
        self.room_id = room_id


class NewMessage(TxtMessage):
    def __init__(self, room_id: str, message: Message) -> None:
        super().__init__()
        self.room_id = room_id
        self.message = message


class RoomsUpdated(TxtMessage):
    def __init__(self, rooms: dict[str, Room]) -> None:
        super().__init__()
        self.rooms = rooms


class TypingUpdated(TxtMessage):
    def __init__(self, room_id: str, users: list[str]) -> None:
        super().__init__()
        self.room_id = room_id
        self.users = users


class StatusChanged(TxtMessage):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class RoomList(Widget):
    DEFAULT_CSS = """
    RoomList {
        width: 28;
        border: solid $primary;
        padding: 0 1;
    }
    RoomList > Label {
        color: $text-muted;
        text-style: bold;
        padding: 0 0 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Rooms")
        yield ListView(id="room_listview")

    def update_rooms(self, rooms: dict[str, Room]) -> None:
        lv = self.query_one("#room_listview", ListView)
        current_items = {item.id for item in lv.query(ListItem)}
        # Add new rooms
        for room_id, room in rooms.items():
            safe_id = room_id.replace(":", "_").replace("!", "_").replace(".", "_")
            widget_id = f"room_{safe_id}"
            if widget_id not in current_items:
                item = ListItem(Label(room.display_name[:22]), id=widget_id)
                item._room_id = room_id  # type: ignore[attr-defined]
                lv.append(item)

    def get_room_id_for_index(self, index: int) -> str | None:
        lv = self.query_one("#room_listview", ListView)
        items = list(lv.query(ListItem))
        if 0 <= index < len(items):
            return getattr(items[index], "_room_id", None)
        return None


class MessagePane(Widget):
    DEFAULT_CSS = """
    MessagePane {
        border: solid $primary;
        padding: 0 1;
    }
    MessagePane > Label#room_title {
        text-style: bold;
        color: $accent;
        padding: 0 0 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Select a room", id="room_title")
        yield RichLog(id="message_log", wrap=True, highlight=False, markup=True)

    def set_title(self, title: str) -> None:
        self.query_one("#room_title", Label).update(title)

    def append_message(self, msg: Message, current_user: str) -> None:
        log = self.query_one("#message_log", RichLog)
        ts = datetime.fromtimestamp(msg.timestamp / 1000, tz=timezone.utc).strftime("%H:%M")
        sender_display = msg.sender.split(":")[0].lstrip("@")
        is_me = msg.sender == current_user

        if msg.redacted:
            line = f"[dim]{ts}[/dim]  [red strikethrough]{sender_display}[/red strikethrough]: [dim italic][Message deleted][/dim italic]"
        else:
            body = msg.edited_body or msg.body
            color = "cyan" if is_me else "green"
            line = f"[dim]{ts}[/dim]  [{color}]{sender_display}[/{color}]: {body}"
            if msg.reactions:
                rxn_parts = [f"{k}×{len(v)}" for k, v in msg.reactions.items()]
                line += f"  [dim]({' '.join(rxn_parts)})[/dim]"

        log.write(line)

    def clear(self) -> None:
        self.query_one("#message_log", RichLog).clear()

    def load_room(self, room: Room, current_user: str) -> None:
        self.clear()
        self.set_title(room.display_name)
        for msg in room.messages:
            self.append_message(msg, current_user)


class TypingBar(Static):
    DEFAULT_CSS = """
    TypingBar {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def update_typing(self, users: list[str], current_user: str) -> None:
        others = [u.split(":")[0].lstrip("@") for u in users if u != current_user]
        if others:
            self.update(f"[dim italic]{', '.join(others)} {'is' if len(others)==1 else 'are'} typing…[/dim italic]")
        else:
            self.update("")


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        color: $text-muted;
        padding: 0 1;
        background: $surface;
    }
    """


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------


class MatrixApp(App):
    """Matrix TUI client."""

    TITLE = "Matrix TUI"
    CSS = """
    Screen {
        layout: vertical;
    }
    #main_area {
        layout: horizontal;
        height: 1fr;
    }
    #right_panel {
        layout: vertical;
        width: 1fr;
    }
    MessagePane {
        height: 1fr;
    }
    TypingBar {
        height: 1;
    }
    #input_row {
        layout: horizontal;
        height: 3;
        padding: 0 1;
    }
    #msg_input {
        width: 1fr;
    }
    #send_label {
        width: 12;
        height: 3;
        content-align: center middle;
        color: $accent;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+j", "next_room", "Next room"),
        Binding("ctrl+k", "prev_room", "Prev room"),
        Binding("ctrl+l", "focus_input", "Focus input"),
        Binding("escape", "focus_rooms", "Focus rooms"),
        Binding("f5", "load_history", "Load history"),
    ]

    current_room_id: reactive[str | None] = reactive(None)

    def __init__(self, matrix_client: MatrixClient, config: AppConfig) -> None:
        super().__init__()
        self._matrix = matrix_client
        self._config = config
        self._typing_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main_area"):
            yield RoomList(id="room_list")
            with Vertical(id="right_panel"):
                yield MessagePane(id="msg_pane")
                yield TypingBar("", id="typing_bar")
                with Horizontal(id="input_row"):
                    yield Input(placeholder="Type a message…", id="msg_input")
                    yield Label("[Enter] Send", id="send_label")
        yield StatusBar("Connecting…", id="status_bar")
        yield Footer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_mount(self) -> None:
        # Register client callbacks
        self._matrix.on_message(self._handle_incoming_message)
        self._matrix.on_room_update(self._handle_room_update)
        self._matrix.on_typing(self._handle_typing)
        self._matrix.on_read_receipt(self._handle_read_receipt)

        # Async startup
        asyncio.create_task(self._startup())

    async def _startup(self) -> None:
        self.post_message(StatusChanged("Syncing rooms…"))
        await self._matrix.initial_sync()
        rooms = self._matrix.rooms
        self.post_message(RoomsUpdated(rooms))
        self.post_message(StatusChanged(f"Ready — {len(rooms)} rooms"))
        self._matrix.start_sync()

    # ------------------------------------------------------------------
    # Matrix callbacks (called from background tasks → must use post_message)
    # ------------------------------------------------------------------

    def _handle_incoming_message(self, room_id: str, msg: Message) -> None:
        self.post_message(NewMessage(room_id, msg))

    def _handle_room_update(self, room_id: str, room: Room) -> None:
        self.post_message(RoomsUpdated(self._matrix.rooms))

    def _handle_typing(self, room_id: str, users: list[str]) -> None:
        self.post_message(TypingUpdated(room_id, users))

    def _handle_read_receipt(self, room_id: str, user_id: str, event_id: str) -> None:
        # Could display read receipt markers; currently just logged
        logger.debug("Read receipt: %s read %s in %s", user_id, event_id, room_id)

    # ------------------------------------------------------------------
    # Message handlers (Textual message system)
    # ------------------------------------------------------------------

    def on_rooms_updated(self, evt: RoomsUpdated) -> None:
        room_list = self.query_one("#room_list", RoomList)
        room_list.update_rooms(evt.rooms)

    def on_new_message(self, evt: NewMessage) -> None:
        if evt.room_id == self.current_room_id:
            pane = self.query_one("#msg_pane", MessagePane)
            pane.append_message(evt.message, self._config.user_id)

    def on_typing_updated(self, evt: TypingUpdated) -> None:
        if evt.room_id == self.current_room_id:
            bar = self.query_one("#typing_bar", TypingBar)
            bar.update_typing(evt.users, self._config.user_id)

    def on_status_changed(self, evt: StatusChanged) -> None:
        self.query_one("#status_bar", StatusBar).update(evt.text)

    # ------------------------------------------------------------------
    # Room selection
    # ------------------------------------------------------------------

    def on_list_view_selected(self, evt: ListView.Selected) -> None:
        room_id = getattr(evt.item, "_room_id", None)
        if room_id:
            self.current_room_id = room_id
            room = self._matrix.rooms.get(room_id)
            if room:
                pane = self.query_one("#msg_pane", MessagePane)
                pane.load_room(room, self._config.user_id)
                # Send read receipt for latest message
                if room.messages:
                    asyncio.create_task(
                        self._matrix.send_read_receipt(room_id, room.messages[-1].event_id)
                    )

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    async def on_input_submitted(self, evt: Input.Submitted) -> None:
        body = evt.value.strip()
        if not body or not self.current_room_id:
            return
        evt.input.value = ""
        # Cancel typing indicator
        await self._send_stop_typing()
        await self._matrix.send_message(self.current_room_id, body)

    async def on_input_changed(self, evt: Input.Changed) -> None:
        if not self.current_room_id:
            return
        if evt.value:
            await self._matrix.send_typing(self.current_room_id, True)
            # Auto-cancel typing after 4s if no more input
            if self._typing_task:
                self._typing_task.cancel()
            self._typing_task = asyncio.create_task(self._auto_cancel_typing())
        else:
            await self._send_stop_typing()

    async def _auto_cancel_typing(self) -> None:
        await asyncio.sleep(4.0)
        await self._send_stop_typing()

    async def _send_stop_typing(self) -> None:
        if self._typing_task:
            self._typing_task.cancel()
            self._typing_task = None
        if self.current_room_id:
            await self._matrix.send_typing(self.current_room_id, False)

    # ------------------------------------------------------------------
    # Actions (keybindings)
    # ------------------------------------------------------------------

    def action_next_room(self) -> None:
        lv = self.query_one("#room_listview", ListView)
        lv.action_cursor_down()

    def action_prev_room(self) -> None:
        lv = self.query_one("#room_listview", ListView)
        lv.action_cursor_up()

    def action_focus_input(self) -> None:
        self.query_one("#msg_input", Input).focus()

    def action_focus_rooms(self) -> None:
        self.query_one("#room_listview", ListView).focus()

    async def action_load_history(self) -> None:
        if not self.current_room_id:
            return
        msgs = await self._matrix.load_more_messages(self.current_room_id)
        if msgs:
            pane = self.query_one("#msg_pane", MessagePane)
            room = self._matrix.rooms[self.current_room_id]
            # Prepend messages to room and reload pane
            room.messages = msgs + room.messages
            pane.load_room(room, self._config.user_id)

    async def action_quit(self) -> None:
        await self._matrix.close()
        self.exit()
