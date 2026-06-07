"""Async Matrix client wrapping matrix-nio."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable

from nio import (
    AsyncClient,
    AsyncClientConfig,
    InviteMemberEvent,
    JoinResponse,
    LoginResponse,
    MatrixRoom,
    MessageDirection,
    RedactionEvent,
    RoomMessage,
    RoomMessageAudio,
    RoomMessageEmote,
    RoomMessageFile,
    RoomMessageImage,
    RoomMessageNotice,
    RoomMessagesResponse,
    RoomMessageVideo,
    RoomNameEvent,
    RoomSendResponse,
    SyncResponse,
    TypingNoticeEvent,
    UnknownEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class Message:
    event_id: str
    sender: str
    body: str
    timestamp: int  # milliseconds since epoch
    is_me: bool = False
    msgtype: str = "m.text"
    mentions_me: bool = False  # True if body contains the local user's display name or MXID


@dataclass
class RoomSummary:
    room_id: str
    display_name: str
    unread_count: int = 0
    last_message: str = ""
    last_ts: int = 0
    member_count: int = 0
    members: list[str] = field(default_factory=list)


class MatrixClient:
    """Thin async wrapper around nio.AsyncClient.

    Extension points:
    - on_room_update(cb): called with room_id whenever a room's metadata changes
    - on_message(cb): called with (room_id, Message) for every new message
    - on_typing(cb): called with (room_id, [user_id, ...]) when typing changes
    """

    def __init__(self, homeserver: str, user_id: str) -> None:
        config = AsyncClientConfig(max_limit_exceeded=0, max_timeouts=0)
        self._client = AsyncClient(homeserver, user_id, config=config)
        self.user_id = user_id
        self.rooms: dict[str, RoomSummary] = {}
        self.messages: dict[str, list[Message]] = {}
        self.typing_users: dict[str, list[str]] = {}
        self.invites: dict[str, str] = {}  # room_id -> inviter user_id
        self._sync_task: asyncio.Task | None = None
        self._on_room_update: list[Callable[[str], None]] = []
        self._on_message: list[Callable[[str, Message], None]] = []
        self._on_typing: list[Callable[[str, list[str]], None]] = []
        self._on_invite: list[Callable[[str, str], None]] = []
        self._running = False

        # RoomMessage matches all subtypes (Text, Image, File, Emote, Notice, …)
        self._client.add_event_callback(self._on_room_message, RoomMessage)
        self._client.add_event_callback(self._on_room_name, RoomNameEvent)
        self._client.add_event_callback(self._on_typing_notice, TypingNoticeEvent)
        self._client.add_event_callback(self._on_redaction, RedactionEvent)
        self._client.add_event_callback(self._on_unknown_event, UnknownEvent)
        self._client.add_event_callback(self._on_invite_event, InviteMemberEvent)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self, password: str) -> None:
        resp = await self._client.login(password, device_name="matrixtui")
        if not isinstance(resp, LoginResponse):
            raise RuntimeError(f"Login failed: {resp}")
        logger.info("Logged in as %s", self.user_id)
        # Persist session so next start can restore without re-login
        try:
            from .session import save_session
            save_session(
                self._client.homeserver,
                self.user_id,
                self._client.access_token,
                self._client.device_id or "",
            )
        except Exception as exc:
            logger.debug("Could not save session: %s", exc)

    def restore_session(self, access_token: str, device_id: str) -> None:
        """Restore a previously saved session without re-authenticating."""
        self._client.access_token = access_token
        self._client.device_id = device_id
        logger.info("Restored session for %s", self.user_id)

    async def logout(self) -> None:
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        if self._client.access_token:
            try:
                await self._client.logout()
            except Exception:
                pass
        await self._client.close()

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    async def start_sync(self) -> None:
        """Run an initial full sync then start background sync loop."""
        resp = await self._client.sync(timeout=30000, full_state=True)
        if isinstance(resp, SyncResponse):
            self._process_sync(resp)
        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())

    async def _sync_loop(self) -> None:
        while self._running:
            try:
                resp = await self._client.sync(timeout=30000)
                if isinstance(resp, SyncResponse):
                    self._process_sync(resp)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Sync error: %s", exc)
                await asyncio.sleep(5)

    def _process_sync(self, resp: SyncResponse) -> None:
        """Update room metadata after each sync.

        nio's event callbacks handle all message/event ingestion; this method
        only maintains the room list and metadata (display name, member count,
        unread count).
        """
        for room_id, room in self._client.rooms.items():
            summary = self.rooms.get(room_id)
            if summary is None:
                summary = RoomSummary(
                    room_id=room_id,
                    display_name=self._room_name(room),
                    member_count=room.member_count,
                )
                self.rooms[room_id] = summary
                self.messages.setdefault(room_id, [])
            else:
                summary.display_name = self._room_name(room)
                summary.member_count = room.member_count
            summary.unread_count = room.unread_notifications
            for cb in self._on_room_update:
                cb(room_id)

    # ------------------------------------------------------------------
    # nio event callbacks (called during sync processing)
    # ------------------------------------------------------------------

    async def _on_room_message(self, room: MatrixRoom, event: RoomMessage) -> None:
        # Detect m.replace edits sent as RoomMessageText with m.relates_to in source
        content = getattr(event, "source", {}).get("content", {})
        relates = content.get("m.relates_to", {})
        if relates.get("rel_type") == "m.replace":
            new_body = content.get("m.new_content", {}).get("body", "")
            replaces_id = relates.get("event_id")
            msgs = self.messages.get(room.room_id, [])
            for existing in msgs:
                if existing.event_id == replaces_id:
                    existing.body = f"{new_body} [edited]"
                    break
            for cb in self._on_room_update:
                cb(room.room_id)
            return

        msg = self._event_to_message(event)
        msgs = self.messages.setdefault(room.room_id, [])
        if not any(m.event_id == msg.event_id for m in msgs):
            msgs.append(msg)
            msgs.sort(key=lambda m: m.timestamp)
            summary = self.rooms.get(room.room_id)
            if summary:
                summary.last_message = msg.body[:80]
                summary.last_ts = msg.timestamp
            for cb in self._on_message:
                cb(room.room_id, msg)
            for cb in self._on_room_update:
                cb(room.room_id)

    async def _on_room_name(self, room: MatrixRoom, event: RoomNameEvent) -> None:
        summary = self.rooms.get(room.room_id)
        if summary:
            summary.display_name = self._room_name(room)
            for cb in self._on_room_update:
                cb(room.room_id)

    async def _on_typing_notice(self, room: MatrixRoom, event: TypingNoticeEvent) -> None:
        self.typing_users[room.room_id] = [u for u in event.users if u != self.user_id]
        for cb in self._on_typing:
            cb(room.room_id, self.typing_users[room.room_id])

    async def _on_redaction(self, room: MatrixRoom, event: RedactionEvent) -> None:
        """Mark a redacted message in-place so it shows as [redacted]."""
        msgs = self.messages.get(room.room_id, [])
        for msg in msgs:
            if msg.event_id == event.redacts:
                msg.body = "[redacted]"
                msg.msgtype = "m.redacted"
                break
        for cb in self._on_room_update:
            cb(room.room_id)

    async def _on_unknown_event(self, room: MatrixRoom, event: UnknownEvent) -> None:
        """Handle m.room.message edits (m.replace relationship)."""
        if event.type != "m.room.message":
            return
        content = getattr(event, "source", {}).get("content", {})
        relates = content.get("m.relates_to", {})
        if relates.get("rel_type") != "m.replace":
            return
        new_content = content.get("m.new_content", {})
        new_body = new_content.get("body", "")
        replaces_id = relates.get("event_id")
        msgs = self.messages.get(room.room_id, [])
        for msg in msgs:
            if msg.event_id == replaces_id:
                msg.body = f"{new_body} [edited]"
                break
        for cb in self._on_room_update:
            cb(room.room_id)

    async def _on_invite_event(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        """Track incoming invites (membership=invite targeting this user)."""
        if event.membership != "invite" or event.state_key != self.user_id:
            return
        inviter = event.sender
        self.invites[room.room_id] = inviter
        for cb in self._on_invite:
            cb(room.room_id, inviter)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send_message(self, room_id: str, text: str) -> str | None:
        resp = await self._client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": text},
        )
        if isinstance(resp, RoomSendResponse):
            return resp.event_id
        return None

    async def send_emote(self, room_id: str, emote: str) -> str | None:
        """Send an m.emote message (renders as '* username <emote>')."""
        resp = await self._client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.emote", "body": emote},
        )
        if isinstance(resp, RoomSendResponse):
            return resp.event_id
        return None

    async def send_read_receipt(self, room_id: str, event_id: str) -> None:
        """Mark a message as read."""
        try:
            await self._client.room_read_markers(
                room_id=room_id,
                fully_read_event=event_id,
                read_event=event_id,
            )
        except Exception as exc:
            logger.debug("Failed to send read receipt: %s", exc)

    async def join_room(self, room_id_or_alias: str) -> str | None:
        """Join a room by ID or alias. Returns the resolved room_id on success."""
        try:
            resp = await self._client.join(room_id_or_alias)
            if isinstance(resp, JoinResponse):
                return resp.room_id
            logger.warning("join failed: %s", resp)
        except Exception as exc:
            logger.warning("join_room error: %s", exc)
        return None

    async def leave_room(self, room_id: str) -> bool:
        """Leave a room. Returns True on success."""
        try:
            resp = await self._client.room_leave(room_id)
            # RoomLeaveResponse has no error attribute on success
            if hasattr(resp, "transport_response") or not hasattr(resp, "message"):
                self.rooms.pop(room_id, None)
                self.messages.pop(room_id, None)
                return True
        except Exception as exc:
            logger.warning("leave_room error: %s", exc)
        return False

    async def load_history(self, room_id: str, limit: int = 50) -> list[Message]:
        """Load older messages for a room via /messages."""
        start = self._client.rooms[room_id].prev_batch if room_id in self._client.rooms else ""
        resp = await self._client.room_messages(
            room_id,
            start=start,
            limit=limit,
            direction=MessageDirection.back,
        )
        if not isinstance(resp, RoomMessagesResponse):
            return []
        msgs: list[Message] = []
        for event in resp.chunk:
            if isinstance(event, RoomMessage):
                msgs.append(self._event_to_message(event))
        msgs.sort(key=lambda m: m.timestamp)
        existing = self.messages.setdefault(room_id, [])
        existing_ids = {m.event_id for m in existing}
        new = [m for m in msgs if m.event_id not in existing_ids]
        existing[:0] = new  # prepend
        existing.sort(key=lambda m: m.timestamp)
        return new

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _event_to_message(self, event: RoomMessage) -> Message:
        """Convert a nio RoomMessage event to a Message dataclass.

        Non-text types are represented with a bracketed prefix so they're
        clearly identifiable in the UI without needing special rendering.
        """
        body = event.body
        msgtype = "m.text"

        if isinstance(event, RoomMessageImage):
            body = f"[image: {event.body}]"
            msgtype = "m.image"
        elif isinstance(event, RoomMessageFile):
            body = f"[file: {event.body}]"
            msgtype = "m.file"
        elif isinstance(event, RoomMessageVideo):
            body = f"[video: {event.body}]"
            msgtype = "m.video"
        elif isinstance(event, RoomMessageAudio):
            body = f"[audio: {event.body}]"
            msgtype = "m.audio"
        elif isinstance(event, RoomMessageEmote):
            body = f"* {event.body}"
            msgtype = "m.emote"
        elif isinstance(event, RoomMessageNotice):
            msgtype = "m.notice"

        local_part = self.user_id.split(":")[0].lstrip("@").lower()
        body_lower = body.lower()
        mentions = (
            local_part in body_lower
            or self.user_id.lower() in body_lower
        )
        return Message(
            event_id=event.event_id,
            sender=event.sender,
            body=body,
            timestamp=event.server_timestamp,
            is_me=(event.sender == self.user_id),
            msgtype=msgtype,
            mentions_me=mentions and not (event.sender == self.user_id),
        )

    @staticmethod
    def _room_name(room: MatrixRoom) -> str:
        if room.display_name:
            return room.display_name
        if room.name:
            return room.name
        non_self = [m for m in room.users if m != room.own_user_id]
        if non_self:
            user = room.users.get(non_self[0])
            if user and user.display_name:
                return user.display_name
            return non_self[0]
        return room.room_id

    async def get_user_profile(self, user_id: str) -> dict | None:
        """Fetch a user's global profile (display_name, avatar_url).

        Returns a dict with 'display_name' and 'avatar_url' keys (either may
        be None/absent), or None if the request fails.
        """
        try:
            from nio import ProfileGetResponse
            resp = await self._client.get_profile(user_id)
            if isinstance(resp, ProfileGetResponse):
                return {
                    "display_name": resp.displayname,
                    "avatar_url": resp.avatar_url,
                }
        except Exception as exc:
            logger.warning("get_user_profile error: %s", exc)
        return None

    def total_unread(self) -> int:
        """Return the sum of unread_count across all known rooms."""
        return sum(r.unread_count for r in self.rooms.values())

    def get_room_topic(self, room_id: str) -> str | None:
        """Return the current topic for a room, or None if not set."""
        nio_room = self._client.rooms.get(room_id)
        if nio_room is None:
            return None
        return getattr(nio_room, "topic", None) or None

    async def set_display_name(self, display_name: str) -> bool:
        """Set the user's global display name. Returns True on success."""
        try:
            from nio import ProfileSetDisplayNameResponse
            resp = await self._client.set_displayname(display_name)
            return isinstance(resp, ProfileSetDisplayNameResponse)
        except Exception as exc:
            logger.warning("set_display_name error: %s", exc)
            return False

    def search_messages(self, query: str, room_id: str | None = None) -> list[tuple[str, Message]]:
        """Search loaded messages for a query string (case-insensitive).

        Returns a list of (room_id, Message) pairs sorted by timestamp.
        Pass room_id to restrict search to one room.
        """
        query_lower = query.lower()
        results: list[tuple[str, Message]] = []
        rooms_to_search = [room_id] if room_id else list(self.messages.keys())
        for rid in rooms_to_search:
            for msg in self.messages.get(rid, []):
                if query_lower in msg.body.lower() or query_lower in msg.sender.lower():
                    results.append((rid, msg))
        results.sort(key=lambda x: x[1].timestamp)
        return results

    def get_room_members(self, room_id: str) -> list[str]:
        """Return a list of user_ids currently in a room (from nio state)."""
        nio_room = self._client.rooms.get(room_id)
        if nio_room is None:
            return []
        return list(nio_room.users.keys())

    def on_room_update(self, cb: Callable[[str], None]) -> None:
        self._on_room_update.append(cb)

    def on_message(self, cb: Callable[[str, Message], None]) -> None:
        self._on_message.append(cb)

    def on_typing(self, cb: Callable[[str, list[str]], None]) -> None:
        self._on_typing.append(cb)

    def on_invite(self, cb: Callable[[str, str], None]) -> None:
        """Register callback for incoming invites: cb(room_id, inviter_user_id)."""
        self._on_invite.append(cb)

    @property
    def nio_client(self) -> AsyncClient:
        return self._client
