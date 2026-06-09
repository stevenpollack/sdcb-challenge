"""Main Textual TUI application for the Matrix client."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
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

from .config import load_config
from .matrix_client import MatrixClient, Message, Room

logger = logging.getLogger(__name__)


class RoomItem(ListItem):
    """A room entry in the sidebar."""

    def __init__(self, room: Room, unread_count: int = 0) -> None:
        super().__init__()
        self.room = room
        self.unread_count = unread_count

    def compose(self) -> ComposeResult:
        yield Label(self._label())

    def _label(self) -> str:
        name = self.room.display_name or self.room.room_id
        badge = f" ({self.unread_count})" if self.unread_count > 0 else ""
        max_name = 28 - len(badge)
        if len(name) > max_name:
            name = name[:max_name - 3] + "..."
        return name + badge

    def refresh_label(self, room: Room, unread_count: int = 0) -> None:
        self.room = room
        self.unread_count = unread_count
        self.query_one(Label).update(self._label())


class MessageView(RichLog):
    """Scrollable message display."""

    DEFAULT_CSS = """
    MessageView {
        border: solid $accent;
        padding: 0 1;
    }
    """


class StatusBar(Static):
    """Connection / context status at the bottom."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary-darken-2;
        color: $text-muted;
        padding: 0 1;
    }
    """


class MatrixTUIApp(App):
    """Matrix TUI client."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #main {
        layout: horizontal;
        height: 1fr;
    }
    #sidebar {
        width: 32;
        border-right: solid $accent-darken-2;
        background: $surface;
    }
    #sidebar-title {
        height: 1;
        background: $primary-darken-3;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    #room-list {
        height: 1fr;
    }
    #chat-area {
        width: 1fr;
        layout: vertical;
    }
    #room-header {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    #message-view {
        height: 1fr;
    }
    #input-row {
        height: 3;
        layout: horizontal;
        padding: 0 1;
    }
    #message-input {
        width: 1fr;
    }
    #send-hint {
        width: 18;
        height: 3;
        padding: 1 1;
        color: $text-muted;
    }
    StatusBar {
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+j", "focus_rooms", "Rooms"),
        Binding("ctrl+k", "focus_input", "Input"),
        Binding("ctrl+r", "join_room", "Join Room"),
        Binding("escape", "cancel_input", "Cancel", show=False),
    ]

    TITLE = "Matrix TUI"
    SUB_TITLE = "connecting..."

    current_room: reactive[Optional[Room]] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        self._config = load_config()
        self._matrix: Optional[MatrixClient] = None
        self._rooms: list[Room] = []
        self._joining = False
        self._typing_users: dict[str, list[str]] = {}  # room_id -> [user_ids]

    # ------------------------------------------------------------------ compose

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield Label("Rooms", id="sidebar-title")
                yield ListView(id="room-list")
            with Vertical(id="chat-area"):
                yield Label("Select a room →", id="room-header")
                yield MessageView(id="message-view", wrap=True, markup=False, max_lines=500)
                with Horizontal(id="input-row"):
                    yield Input(placeholder="Type a message…", id="message-input")
                    yield Label("Enter ↵ to send", id="send-hint")
        yield StatusBar("Not connected", id="status-bar")
        yield Footer()

    # ------------------------------------------------------------------ lifecycle

    def on_mount(self) -> None:
        self._set_status("Connecting…")
        self.run_worker(self._connect(), name="connect", exit_on_error=False)

    @work(exit_on_error=False)
    async def _connect(self) -> None:
        cfg = self._config
        if not cfg["user"] or not cfg["password"]:
            self._set_status("ERROR: MATRIX_USER / MATRIX_PASSWORD not set")
            return

        self._matrix = MatrixClient(
            homeserver=cfg["homeserver"],
            user_id=cfg["user"],
            password=cfg["password"],
            on_message=self._handle_message,
            on_room_update=self._handle_room_update,
            on_typing=self._handle_typing,
        )
        try:
            await self._matrix.login()
        except Exception as exc:
            self._set_status(f"Login failed: {exc}")
            return

        self._set_status(f"Logged in as {cfg['user']}")
        self.sub_title = cfg["user"]

        # Initial sync so rooms have display names and we establish next_batch
        await self._matrix._client.sync(timeout=10000)

        # Load initial rooms and update UI directly (we're in the event loop)
        rooms = await self._matrix.get_rooms()
        self._on_rooms_updated(rooms)

        # Start real-time sync
        await self._matrix.start_sync()

    # ------------------------------------------------------------------ message handlers
    # nio callbacks fire as coroutines inside the same asyncio event loop that
    # Textual owns. call_from_thread() is only for actual OS threads. Use
    # call_later() to schedule a synchronous UI update on the next tick.

    def _handle_message(self, msg: Message) -> None:
        self.call_later(self._on_message_received, msg)

    def _on_message_received(self, msg: Message) -> None:
        if self.current_room and msg.room_id == self.current_room.room_id:
            self._append_message(msg)
        else:
            # Refresh sidebar to show updated unread badge
            self._refresh_room_list()

    def _handle_typing(self, room_id: str, typers: list[str]) -> None:
        self.call_later(self._on_typing_updated, room_id, typers)

    def _on_typing_updated(self, room_id: str, typers: list[str]) -> None:
        self._typing_users[room_id] = typers
        if self.current_room and self.current_room.room_id == room_id:
            self._update_typing_status()

    def _handle_room_update(self, rooms: list[Room]) -> None:
        self.call_later(self._on_rooms_updated, rooms)

    def _on_rooms_updated(self, rooms: list[Room]) -> None:
        self._rooms = rooms
        self._refresh_room_list()

    def _refresh_room_list(self) -> None:
        lv = self.query_one("#room-list", ListView)
        current_id = self.current_room.room_id if self.current_room else None

        lv.clear()
        selected_index = None
        unread = self._matrix.unread_counts if self._matrix else {}
        for i, room in enumerate(sorted(self._rooms, key=lambda r: r.display_name.lower())):
            item = RoomItem(room, unread_count=unread.get(room.room_id, 0))
            lv.append(item)
            if room.room_id == current_id:
                selected_index = i

        if selected_index is not None:
            lv.index = selected_index

    # ------------------------------------------------------------------ UI helpers

    def _update_typing_status(self) -> None:
        if not self.current_room:
            return
        typers = self._typing_users.get(self.current_room.room_id, [])
        if typers and self._matrix:
            names = ", ".join(self._matrix.get_display_name(u) for u in typers[:3])
            suffix = " are typing…" if len(typers) > 1 else " is typing…"
            self._set_status(names + suffix)
        else:
            # Restore connected status
            user = self._config.get("user", "")
            if self._matrix and self._matrix.connected:
                self._set_status(f"Logged in as {user}")

    def _append_message(self, msg: Message) -> None:
        view = self.query_one("#message-view", MessageView)
        ts = ""
        if msg.timestamp:
            ts = datetime.fromtimestamp(msg.timestamp / 1000).strftime("%H:%M")
        if self._matrix:
            sender = self._matrix.get_display_name(msg.sender)
        else:
            sender = msg.sender
        is_self = msg.sender == self._config.get("user", "")
        prefix = "→" if is_self else " "
        view.write(f"[{ts}] {prefix} {sender}: {msg.body}")

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#status-bar", StatusBar).update(text)
        except Exception:
            pass

    # ------------------------------------------------------------------ events

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, RoomItem):
            return
        room = event.item.room
        self.current_room = room
        self.query_one("#room-header", Label).update(f"# {room.display_name}")
        view = self.query_one("#message-view", MessageView)
        view.clear()
        view.write(f"--- {room.display_name} ---")
        # Clear unread count for this room
        if self._matrix:
            self._matrix.clear_unread(room.room_id)
        self._refresh_room_list()
        self.run_worker(self._load_history(room.room_id), name="history", exit_on_error=False)
        self.query_one("#message-input", Input).focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Send typing notification when user types."""
        if event.input.id != "message-input" or not self.current_room or not self._matrix:
            return
        typing = bool(event.value)
        self.run_worker(
            self._matrix.send_typing(self.current_room.room_id, typing),
            name="typing",
            exit_on_error=False,
        )

    @work(exit_on_error=False)
    async def _load_history(self, room_id: str) -> None:
        if not self._matrix:
            return
        try:
            messages = await self._matrix.get_room_history(room_id, limit=50)
            self.call_from_thread(self._on_history_loaded, room_id, messages)
        except Exception as exc:
            logger.warning("History load failed: %s", exc)

    def _on_history_loaded(self, room_id: str, messages: list[Message]) -> None:
        if not self.current_room or self.current_room.room_id != room_id:
            return
        view = self.query_one("#message-view", MessageView)
        for msg in messages:
            self._append_message(msg)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        input_widget = self.query_one("#message-input", Input)
        input_widget.value = ""

        if not self._matrix:
            self._set_status("Not connected")
            return
        if not self.current_room:
            self._set_status("No room selected")
            return

        self.run_worker(
            self._send_message(self.current_room.room_id, text),
            name="send",
            exit_on_error=False,
        )

    @work(exit_on_error=False)
    async def _send_message(self, room_id: str, body: str) -> None:
        if not self._matrix:
            return
        try:
            await self._matrix.send_message(room_id, body)
        except Exception as exc:
            self.call_from_thread(self._set_status, f"Send failed: {exc}")

    # ------------------------------------------------------------------ actions

    def action_focus_rooms(self) -> None:
        self.query_one("#room-list", ListView).focus()

    def action_focus_input(self) -> None:
        self.query_one("#message-input", Input).focus()

    def action_cancel_input(self) -> None:
        self.query_one("#message-input", Input).value = ""

    def action_join_room(self) -> None:
        self.run_worker(self._prompt_join(), name="join-prompt", exit_on_error=False)

    @work(exit_on_error=False)
    async def _prompt_join(self) -> None:
        from textual.widgets import Input as TInput
        # Simple inline join: push a modal-like overlay using app.push_screen
        self.call_from_thread(self._show_join_dialog)

    def _show_join_dialog(self) -> None:
        self.push_screen(JoinRoomScreen(self._do_join))

    def _do_join(self, room_alias: str) -> None:
        self.run_worker(self._join_room_async(room_alias), name="join", exit_on_error=False)

    @work(exit_on_error=False)
    async def _join_room_async(self, room_alias: str) -> None:
        if not self._matrix:
            return
        try:
            room_id = await self._matrix.join_room(room_alias)
            rooms = await self._matrix.get_rooms()
            self.call_from_thread(self._handle_room_update_direct, rooms, room_id)
        except Exception as exc:
            self.call_from_thread(self._set_status, f"Join failed: {exc}")

    def _handle_room_update_direct(self, rooms: list[Room], focus_id: str) -> None:
        self._on_rooms_updated(rooms)
        # Find and select the newly joined room
        for item in self.query("#room-list ListItem").results(RoomItem):
            if item.room.room_id == focus_id:
                lv = self.query_one("#room-list", ListView)
                lv.index = list(self.query("#room-list ListItem").results(RoomItem)).index(item)
                break

    async def on_unmount(self) -> None:
        if self._matrix:
            await self._matrix.stop()


class JoinRoomScreen(App):
    """Modal-style overlay to join a room by alias or ID.

    Because Textual's Screen system works differently, we implement this
    as a separate screen pushed onto the app's screen stack.
    """
    pass


from textual.screen import Screen as TScreen


class JoinRoomScreen(TScreen):
    """Overlay to enter a room alias or ID."""

    CSS = """
    JoinRoomScreen {
        align: center middle;
    }
    #join-dialog {
        width: 60;
        height: 10;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #join-label {
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
    ]

    def __init__(self, on_join: callable) -> None:
        super().__init__()
        self._on_join = on_join

    def compose(self) -> ComposeResult:
        with Vertical(id="join-dialog"):
            yield Label("Enter room alias or ID (e.g. #room:matrix.org):", id="join-label")
            yield Input(placeholder="#room:matrix.org", id="join-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        alias = event.value.strip()
        if alias:
            self.dismiss()
            self._on_join(alias)
        else:
            self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()


def main() -> None:
    """Entry point."""
    app = MatrixTUIApp()
    app.run()


if __name__ == "__main__":
    main()
