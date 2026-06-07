"""Textual TUI application for Matrix."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message as TMessage
from textual.reactive import reactive
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

from .client import MatrixClient, Message, RoomSummary
from .config import Config

logger = logging.getLogger(__name__)

# Colour per message type (Textual markup colours)
_MSGTYPE_COLOUR = {
    "m.image": "yellow",
    "m.file": "yellow",
    "m.video": "yellow",
    "m.audio": "yellow",
    "m.emote": "italic magenta",
    "m.notice": "dim",
}


class RoomUpdated(TMessage):
    def __init__(self, room_id: str) -> None:
        super().__init__()
        self.room_id = room_id


class NewMessage(TMessage):
    def __init__(self, room_id: str, msg: Message) -> None:
        super().__init__()
        self.room_id = room_id
        self.msg = msg


class TypingUpdated(TMessage):
    def __init__(self, room_id: str, users: list[str]) -> None:
        super().__init__()
        self.room_id = room_id
        self.users = users


class RoomListItem(ListItem):
    def __init__(self, summary: RoomSummary) -> None:
        super().__init__()
        self.summary = summary
        self._label = Label(self._text())
        self._room_id = summary.room_id

    def _text(self) -> str:
        unread = f" [{self.summary.unread_count}]" if self.summary.unread_count else ""
        name = self.summary.display_name or self.summary.room_id
        if len(name) > 26:
            name = name[:23] + "…"
        return f"{name}{unread}"

    def compose(self) -> ComposeResult:
        yield self._label

    def refresh_text(self) -> None:
        self._label.update(self._text())


class MatrixApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #main {
        layout: horizontal;
        height: 1fr;
    }
    #left-pane {
        width: 30;
        layout: vertical;
        height: 100%;
        border-right: solid $primary;
    }
    #room-filter {
        height: 3;
        border-bottom: solid $primary-darken-2;
    }
    #room-filter-input {
        width: 1fr;
    }
    #room-list {
        height: 1fr;
    }
    #right-pane {
        width: 1fr;
        layout: vertical;
        height: 100%;
    }
    #room-title {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    #messages {
        height: 1fr;
        border: none;
    }
    #typing-indicator {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    #input-bar {
        height: 3;
        border-top: solid $primary;
        padding: 1 0 0 0;
    }
    #msg-input {
        width: 1fr;
    }
    #status-bar {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+r", "reload_history", "History", show=True),
        Binding("ctrl+f", "focus_filter", "Filter rooms", show=True),
        Binding("escape", "focus_input", "Focus input", show=False),
    ]

    current_room: reactive[str | None] = reactive(None)
    _filter_text: reactive[str] = reactive("")

    def __init__(self, client: MatrixClient) -> None:
        super().__init__()
        self._client = client
        self._room_items: dict[str, RoomListItem] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="left-pane"):
                with Horizontal(id="room-filter"):
                    yield Input(placeholder="Filter rooms…", id="room-filter-input")
                yield ListView(id="room-list")
            with Vertical(id="right-pane"):
                yield Static("Select a room", id="room-title")
                yield RichLog(id="messages", highlight=True, markup=True, wrap=True)
                yield Static("", id="typing-indicator")
                with Horizontal(id="input-bar"):
                    yield Input(placeholder="Type a message…", id="msg-input")
        yield Static("Connecting…", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self._client.on_room_update(self._schedule_room_update)
        self._client.on_message(self._schedule_new_message)
        self._client.on_typing(self._schedule_typing_update)
        self.run_worker(self._connect(), exclusive=True, name="matrix-sync")

    async def _connect(self) -> None:
        try:
            cfg = Config.from_env()
            self.query_one("#status-bar", Static).update("Logging in…")
            await self._client.login(cfg.password)
            self.query_one("#status-bar", Static).update("Syncing…")
            await self._client.start_sync()
            self.query_one("#status-bar", Static).update(
                f"Connected as {self._client.user_id}"
            )
            self._rebuild_room_list()
        except Exception as exc:
            self.query_one("#status-bar", Static).update(f"Error: {exc}")
            logger.exception("Connection failed")

    # ------------------------------------------------------------------
    # Scheduled message handlers (bridge sync thread → Textual event loop)
    # ------------------------------------------------------------------

    def _schedule_room_update(self, room_id: str) -> None:
        self.post_message(RoomUpdated(room_id))

    def _schedule_new_message(self, room_id: str, msg: Message) -> None:
        self.post_message(NewMessage(room_id, msg))

    def _schedule_typing_update(self, room_id: str, users: list[str]) -> None:
        self.post_message(TypingUpdated(room_id, users))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_room_updated(self, event: RoomUpdated) -> None:
        self._rebuild_room_list()

    def on_new_message(self, event: NewMessage) -> None:
        item = self._room_items.get(event.room_id)
        if item:
            item.refresh_text()
        if self.current_room == event.room_id:
            self._append_message(event.msg)

    def on_typing_updated(self, event: TypingUpdated) -> None:
        if self.current_room != event.room_id:
            return
        indicator = self.query_one("#typing-indicator", Static)
        if event.users:
            names = ", ".join(u.split(":")[0].lstrip("@") for u in event.users[:3])
            suffix = " are typing…" if len(event.users) > 1 else " is typing…"
            indicator.update(f"{names}{suffix}")
        else:
            indicator.update("")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "room-filter-input":
            self._filter_text = event.value.lower()
            self._apply_filter()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, RoomListItem):
            self.current_room = event.item._room_id
            self._load_room(event.item._room_id)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "room-filter-input":
            # Move focus to room list on Enter in filter
            self.query_one("#room-list", ListView).focus()
            return
        text = event.value.strip()
        if not text or not self.current_room:
            return
        event.input.clear()
        await self._client.send_message(self.current_room, text)

    # ------------------------------------------------------------------
    # Room list management
    # ------------------------------------------------------------------

    def _rebuild_room_list(self) -> None:
        lv = self.query_one("#room-list", ListView)
        rooms = sorted(
            self._client.rooms.values(),
            key=lambda r: r.last_ts,
            reverse=True,
        )
        for summary in rooms:
            if summary.room_id not in self._room_items:
                item = RoomListItem(summary)
                self._room_items[summary.room_id] = item
                lv.append(item)
            else:
                self._room_items[summary.room_id].refresh_text()
        self._apply_filter()

    def _apply_filter(self) -> None:
        ftext = self._filter_text
        for room_id, item in self._room_items.items():
            name = (self._client.rooms[room_id].display_name or room_id).lower()
            item.display = not ftext or ftext in name

    # ------------------------------------------------------------------
    # Message display
    # ------------------------------------------------------------------

    def _load_room(self, room_id: str) -> None:
        summary = self._client.rooms.get(room_id)
        members = f" ({summary.member_count})" if summary and summary.member_count else ""
        title = (summary.display_name if summary else room_id) + members
        self.query_one("#room-title", Static).update(title)
        self.query_one("#typing-indicator", Static).update("")
        log = self.query_one("#messages", RichLog)
        log.clear()
        msgs = self._client.messages.get(room_id, [])
        for msg in msgs:
            self._append_message(msg)
        self.query_one("#msg-input", Input).focus()
        # Send read receipt for last message
        if msgs:
            self.run_worker(
                self._client.send_read_receipt(room_id, msgs[-1].event_id),
                name="read-receipt",
            )

    def _append_message(self, msg: Message) -> None:
        log = self.query_one("#messages", RichLog)
        ts = datetime.fromtimestamp(msg.timestamp / 1000, tz=timezone.utc).strftime("%H:%M")
        sender_short = msg.sender.split(":")[0].lstrip("@")

        colour = _MSGTYPE_COLOUR.get(msg.msgtype, "cyan" if msg.is_me else "green")
        line = f"[bold {colour}]{ts} {sender_short}[/bold {colour}]: {msg.body}"
        log.write(line)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def action_reload_history(self) -> None:
        if not self.current_room:
            return
        await self._client.load_history(self.current_room)
        self._load_room(self.current_room)

    def action_focus_input(self) -> None:
        self.query_one("#msg-input", Input).focus()

    def action_focus_filter(self) -> None:
        self.query_one("#room-filter-input", Input).focus()

    async def action_quit(self) -> None:
        await self._client.logout()
        self.exit()
