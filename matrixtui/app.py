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


class InviteReceived(TMessage):
    def __init__(self, room_id: str, inviter: str) -> None:
        super().__init__()
        self.room_id = room_id
        self.inviter = inviter


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
                    yield Input(placeholder="Message or /help for commands…", id="msg-input")
        yield Static("Connecting…", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self._client.on_room_update(self._schedule_room_update)
        self._client.on_message(self._schedule_new_message)
        self._client.on_typing(self._schedule_typing_update)
        self._client.on_invite(self._schedule_invite)
        self._show_welcome()
        self.run_worker(self._connect(), exclusive=True, name="matrix-sync")

    def _show_welcome(self) -> None:
        log = self.query_one("#messages", RichLog)
        log.write("[bold]matrixtui[/bold] — Matrix TUI client")
        log.write("")
        log.write("  Select a room from the sidebar to start chatting.")
        log.write("")
        log.write("[bold]Quick reference:[/bold]")
        log.write("  [dim]/help[/dim]          Show all commands and keybindings")
        log.write("  [dim]/join #room:srv[/dim] Join a room")
        log.write("  [dim]/search <query>[/dim] Search messages  [dim]/clear[/dim] Clear pane")
        log.write("  [dim]Ctrl+F[/dim]          Filter rooms  [dim]Ctrl+R[/dim] Load history")
        log.write("")

    async def _connect(self) -> None:
        try:
            cfg = Config.from_env()
            self.query_one("#status-bar", Static).update("Logging in…")
            await self._client.login(cfg.password)
            self.query_one("#status-bar", Static).update("Syncing…")
            await self._client.start_sync()
            self._rebuild_room_list()
            self._update_status()
        except Exception as exc:
            self.query_one("#status-bar", Static).update(f"Error: {exc}")
            logger.exception("Connection failed")

    def _update_status(self) -> None:
        unread = self._client.total_unread()
        badge = f"  [{unread} unread]" if unread else ""
        self.query_one("#status-bar", Static).update(
            f"Connected as {self._client.user_id}{badge}"
        )

    # ------------------------------------------------------------------
    # Scheduled message handlers (bridge sync thread → Textual event loop)
    # ------------------------------------------------------------------

    def _schedule_room_update(self, room_id: str) -> None:
        self.post_message(RoomUpdated(room_id))

    def _schedule_new_message(self, room_id: str, msg: Message) -> None:
        self.post_message(NewMessage(room_id, msg))

    def _schedule_typing_update(self, room_id: str, users: list[str]) -> None:
        self.post_message(TypingUpdated(room_id, users))

    def _schedule_invite(self, room_id: str, inviter: str) -> None:
        self.post_message(InviteReceived(room_id, inviter))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_room_updated(self, event: RoomUpdated) -> None:
        self._rebuild_room_list()
        if self._client.user_id:
            self._update_status()

    def on_new_message(self, event: NewMessage) -> None:
        item = self._room_items.get(event.room_id)
        if item:
            item.refresh_text()
        if self.current_room == event.room_id:
            self._append_message(event.msg)

    def on_invite_received(self, event: InviteReceived) -> None:
        inviter_short = event.inviter.split(":")[0].lstrip("@")
        self.query_one("#status-bar", Static).update(
            f"Invite from {inviter_short} to {event.room_id} — type /join {event.room_id} to accept"
        )

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
            self.query_one("#room-list", ListView).focus()
            return
        text = event.value.strip()
        if not text:
            return
        event.input.clear()

        # Slash commands
        if text.startswith("/join "):
            alias = text[6:].strip()
            await self._handle_join(alias)
        elif text.startswith("/leave"):
            await self._handle_leave()
        elif text.startswith("/search "):
            query = text[8:].strip()
            self._handle_search(query)
        elif text.startswith("/members"):
            self._handle_members()
        elif text.startswith("/topic"):
            self._handle_topic()
        elif text.startswith("/nick "):
            name = text[6:].strip()
            await self._handle_nick(name)
        elif text.startswith("/help"):
            self._handle_help()
        elif text.startswith("/me "):
            emote = text[4:].strip()
            await self._handle_me(emote)
        elif text.startswith("/whois "):
            target = text[7:].strip()
            await self._handle_whois(target)
        elif text.startswith("/invite "):
            target = text[8:].strip()
            await self._handle_invite(target)
        elif text.startswith("/kick "):
            target = text[6:].strip()
            await self._handle_kick(target)
        elif text == "/clear":
            self._handle_clear()
        elif self.current_room:
            await self._client.send_message(self.current_room, text)

    async def _handle_join(self, room_id_or_alias: str) -> None:
        status = self.query_one("#status-bar", Static)
        status.update(f"Joining {room_id_or_alias}…")
        room_id = await self._client.join_room(room_id_or_alias)
        if room_id:
            status.update(f"Joined {room_id_or_alias}")
            # Trigger a sync to populate room
            self._rebuild_room_list()
        else:
            status.update(f"Failed to join {room_id_or_alias}")

    def _handle_search(self, query: str) -> None:
        if not query:
            return
        results = self._client.search_messages(query, room_id=self.current_room)
        log = self.query_one("#messages", RichLog)
        log.clear()
        if not results:
            log.write(f"[dim]No results for '{query}'[/dim]")
            return
        log.write(f"[dim]Search results for '{query}' ({len(results)} found):[/dim]")
        for room_id, msg in results:
            room_name = self._client.rooms.get(room_id, None)
            rname = room_name.display_name if room_name else room_id
            ts = datetime.fromtimestamp(
                msg.timestamp / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M")
            sender_short = msg.sender.split(":")[0].lstrip("@")
            log.write(f"[dim]{rname}[/dim] [{ts}] [bold]{sender_short}[/bold]: {msg.body}")

    async def _handle_whois(self, user_id: str) -> None:
        if not user_id:
            return
        log = self.query_one("#messages", RichLog)
        profile = await self._client.get_user_profile(user_id)
        if profile is None:
            log.write(f"[dim]Could not fetch profile for {user_id}[/dim]")
            return
        display = profile.get("display_name") or "(no display name)"
        avatar = profile.get("avatar_url") or "(no avatar)"
        log.write(f"[bold]{user_id}[/bold]")
        log.write(f"  Display name: {display}")
        log.write(f"  Avatar:       {avatar}")

    async def _handle_invite(self, user_id: str) -> None:
        if not self.current_room or not user_id:
            return
        status = self.query_one("#status-bar", Static)
        ok = await self._client.invite_user(self.current_room, user_id)
        status.update(f"Invited {user_id}" if ok else f"Failed to invite {user_id}")

    async def _handle_kick(self, user_id: str) -> None:
        if not self.current_room or not user_id:
            return
        status = self.query_one("#status-bar", Static)
        ok = await self._client.kick_user(self.current_room, user_id)
        status.update(f"Kicked {user_id}" if ok else f"Failed to kick {user_id}")

    def _handle_clear(self) -> None:
        self.query_one("#messages", RichLog).clear()

    async def _handle_me(self, emote: str) -> None:
        if not self.current_room or not emote:
            return
        await self._client.send_emote(self.current_room, emote)

    def _handle_topic(self) -> None:
        if not self.current_room:
            return
        topic = self._client.get_room_topic(self.current_room)
        log = self.query_one("#messages", RichLog)
        if topic:
            log.write(f"[dim]Topic:[/dim] {topic}")
        else:
            log.write("[dim]No topic set for this room.[/dim]")

    async def _handle_nick(self, name: str) -> None:
        if not name:
            return
        status = self.query_one("#status-bar", Static)
        status.update(f"Setting display name to '{name}'…")
        ok = await self._client.set_display_name(name)
        if ok:
            status.update(f"Display name set to '{name}'")
        else:
            status.update("Failed to set display name")

    def _handle_help(self) -> None:
        log = self.query_one("#messages", RichLog)
        log.clear()
        log.write("[bold]matrixtui — keyboard shortcuts & slash commands[/bold]")
        log.write("")
        log.write("[bold]Keyboard:[/bold]")
        log.write("  Ctrl+F        Focus room filter")
        log.write("  Ctrl+R        Load older message history")
        log.write("  Ctrl+C        Quit")
        log.write("  Esc           Focus message input")
        log.write("")
        log.write("[bold]Slash commands (type in message input):[/bold]")
        log.write("  /help                   Show this help")
        log.write("  /join #alias:server     Join a room by alias or ID")
        log.write("  /leave                  Leave the current room")
        log.write("  /search <query>         Search messages in current room")
        log.write("  /members                List members of current room")
        log.write("  /topic                  Show the current room topic")
        log.write("  /nick <name>            Set your global display name")
        log.write("  /me <action>            Send an emote (e.g. /me waves)")
        log.write("  /whois <@user:srv>      Show a user's display name and avatar")
        log.write("  /invite <@user:srv>     Invite a user to the current room")
        log.write("  /kick <@user:srv>       Kick a user from the current room")
        log.write("  /clear                  Clear the message pane")

    def _handle_members(self) -> None:
        if not self.current_room:
            return
        members = self._client.get_room_members(self.current_room)
        log = self.query_one("#messages", RichLog)
        log.clear()
        log.write(f"[dim]Members ({len(members)}):[/dim]")
        for user_id in sorted(members):
            log.write(f"  {user_id}")

    async def _handle_leave(self) -> None:
        if not self.current_room:
            return
        room_id = self.current_room
        status = self.query_one("#status-bar", Static)
        ok = await self._client.leave_room(room_id)
        if ok:
            # Remove from UI
            item = self._room_items.pop(room_id, None)
            if item:
                await item.remove()
            self.current_room = None
            self.query_one("#room-title", Static).update("Select a room")
            self.query_one("#messages", RichLog).clear()
            status.update("Left room")
        else:
            status.update("Failed to leave room")

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
        # Create any new items first
        for summary in rooms:
            if summary.room_id not in self._room_items:
                item = RoomListItem(summary)
                self._room_items[summary.room_id] = item
                lv.append(item)
            else:
                self._room_items[summary.room_id].refresh_text()
        # Re-order widgets to match sorted order
        for i, summary in enumerate(rooms):
            item = self._room_items[summary.room_id]
            lv.move_child(item, before=i)
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
        self._last_date: str = ""  # reset date-separator state
        for msg in msgs:
            self._append_message(msg)
        self.query_one("#msg-input", Input).focus()
        # Zero unread count locally so badge clears immediately
        if summary:
            summary.unread_count = 0
            item = self._room_items.get(room_id)
            if item:
                item.refresh_text()
        # Send read receipt for last message
        if msgs:
            self.run_worker(
                self._client.send_read_receipt(room_id, msgs[-1].event_id),
                name="read-receipt",
            )

    def _append_message(self, msg: Message) -> None:
        log = self.query_one("#messages", RichLog)
        dt = datetime.fromtimestamp(msg.timestamp / 1000, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        if date_str != getattr(self, "_last_date", ""):
            self._last_date = date_str
            log.write(f"[dim]─── {date_str} ───[/dim]")
        ts = dt.strftime("%H:%M")
        sender_short = msg.sender.split(":")[0].lstrip("@")

        if msg.mentions_me:
            # Highlight the entire line for mentions
            colour = "bold red on dark_red"
            line = f"[{colour}]{ts} {sender_short}: {msg.body}[/{colour}]"
        else:
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
