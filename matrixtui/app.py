"""Textual TUI application for Matrix."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
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
from textual.message import Message as TMessage

from .client import MatrixClient, Message, RoomSummary
from .config import Config

logger = logging.getLogger(__name__)


class RoomUpdated(TMessage):
    def __init__(self, room_id: str) -> None:
        super().__init__()
        self.room_id = room_id


class NewMessage(TMessage):
    def __init__(self, room_id: str, msg: Message) -> None:
        super().__init__()
        self.room_id = room_id
        self.msg = msg


class RoomListItem(ListItem):
    def __init__(self, summary: RoomSummary) -> None:
        super().__init__()
        self.summary = summary
        self._label = Label(self._text())
        self._room_id = summary.room_id

    def _text(self) -> str:
        unread = f" [{self.summary.unread_count}]" if self.summary.unread_count else ""
        name = self.summary.display_name or self.summary.room_id
        if len(name) > 28:
            name = name[:25] + "…"
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
    #room-list {
        width: 30;
        border-right: solid $primary;
        height: 100%;
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
        Binding("escape", "focus_input", "Focus input", show=False),
    ]

    current_room: reactive[str | None] = reactive(None)

    def __init__(self, client: MatrixClient) -> None:
        super().__init__()
        self._client = client
        self._room_items: dict[str, RoomListItem] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            yield ListView(id="room-list")
            with Vertical(id="right-pane"):
                yield Static("Select a room", id="room-title")
                yield RichLog(id="messages", highlight=True, markup=True, wrap=True)
                with Horizontal(id="input-bar"):
                    yield Input(placeholder="Type a message…", id="msg-input")
        yield Static("Connecting…", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self._client.on_room_update(self._schedule_room_update)
        self._client.on_message(self._schedule_new_message)
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

    def _schedule_room_update(self, room_id: str) -> None:
        self.post_message(RoomUpdated(room_id))

    def _schedule_new_message(self, room_id: str, msg: Message) -> None:
        self.post_message(NewMessage(room_id, msg))

    def on_room_updated(self, event: RoomUpdated) -> None:
        self._rebuild_room_list()
        if self.current_room == event.room_id:
            item = self._room_items.get(event.room_id)
            if item:
                item.refresh_text()

    def on_new_message(self, event: NewMessage) -> None:
        item = self._room_items.get(event.room_id)
        if item:
            item.refresh_text()
        if self.current_room == event.room_id:
            self._append_message(event.msg)

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

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, RoomListItem):
            self.current_room = event.item._room_id
            self._load_room(event.item._room_id)

    def _load_room(self, room_id: str) -> None:
        summary = self._client.rooms.get(room_id)
        title = summary.display_name if summary else room_id
        self.query_one("#room-title", Static).update(title)
        log = self.query_one("#messages", RichLog)
        log.clear()
        for msg in self._client.messages.get(room_id, []):
            self._append_message(msg)
        self.query_one("#msg-input", Input).focus()

    def _append_message(self, msg: Message) -> None:
        log = self.query_one("#messages", RichLog)
        ts = datetime.fromtimestamp(msg.timestamp / 1000, tz=timezone.utc).strftime("%H:%M")
        sender_short = msg.sender.split(":")[0].lstrip("@")
        if msg.is_me:
            line = f"[bold cyan]{ts} {sender_short}[/bold cyan]: {msg.body}"
        else:
            line = f"[bold green]{ts} {sender_short}[/bold green]: {msg.body}"
        log.write(line)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text or not self.current_room:
            return
        event.input.clear()
        await self._client.send_message(self.current_room, text)

    async def action_reload_history(self) -> None:
        if not self.current_room:
            return
        await self._client.load_history(self.current_room)
        self._load_room(self.current_room)

    def action_focus_input(self) -> None:
        self.query_one("#msg-input", Input).focus()

    async def action_quit(self) -> None:
        await self._client.logout()
        self.exit()
