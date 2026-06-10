"""Matrix client wrapper around matrix-nio."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nio import (
    AsyncClient,
    AsyncClientConfig,
    KeyVerificationEvent,
    LoginResponse,
    MatrixRoom,
    ReactionEvent,
    RedactionEvent,
    RoomMemberEvent,
    RoomMessage,
    RoomMessageText,
    SyncError,
    SyncResponse,
    TypingNoticeEvent,
)
from nio.responses import RoomMessagesResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Message:
    event_id: str
    sender: str
    body: str
    timestamp: int  # ms since epoch
    msgtype: str = "m.text"
    edited_body: str | None = None
    reactions: dict[str, list[str]] = field(default_factory=dict)  # key -> [sender]
    redacted: bool = False


@dataclass
class Room:
    room_id: str
    display_name: str
    members: list[str] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    unread_count: int = 0
    typing_users: list[str] = field(default_factory=list)
    last_read_event_id: str | None = None


# ---------------------------------------------------------------------------
# Event callbacks type
# ---------------------------------------------------------------------------

RoomUpdateCallback = Callable[[str, Room], None]
MessageCallback = Callable[[str, Message], None]
TypingCallback = Callable[[str, list[str]], None]
ReadReceiptCallback = Callable[[str, str, str], None]  # room_id, user_id, event_id


# ---------------------------------------------------------------------------
# MatrixClient
# ---------------------------------------------------------------------------


class MatrixClient:
    """Thin async wrapper over matrix-nio AsyncClient."""

    def __init__(
        self,
        homeserver: str,
        user_id: str,
        device_name: str = "matrix-tui",
    ) -> None:
        self.homeserver = homeserver
        self.user_id = user_id
        self._device_name = device_name

        config = AsyncClientConfig(
            max_limit_exceeded=0,
            max_timeouts=0,
            store_sync_tokens=True,
            encryption_enabled=False,
        )
        self._nio = AsyncClient(homeserver, user_id, config=config)

        self._rooms: dict[str, Room] = {}
        self._sync_task: asyncio.Task | None = None
        self._running = False

        # Callbacks
        self._on_room_update: list[RoomUpdateCallback] = []
        self._on_message: list[MessageCallback] = []
        self._on_typing: list[TypingCallback] = []
        self._on_read_receipt: list[ReadReceiptCallback] = []

        self._register_callbacks()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def login(self, password: str) -> None:
        resp = await self._nio.login(password, device_name=self._device_name)
        if not isinstance(resp, LoginResponse):
            raise RuntimeError(f"Login failed: {resp}")
        logger.info("Logged in as %s", self.user_id)

    def set_token(self, access_token: str, device_id: str) -> None:
        """Restore session from a previously-obtained access token (no new login request)."""
        self._nio.access_token = access_token
        self._nio.device_id = device_id
        logger.info("Session restored for %s", self.user_id)

    @property
    def access_token(self) -> str:
        return self._nio.access_token

    @property
    def device_id(self) -> str:
        return self._nio.device_id

    async def logout(self) -> None:
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        await self._nio.logout()
        await self._nio.close()

    async def close(self) -> None:
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        await self._nio.close()

    def start_sync(self) -> None:
        """Start background sync loop."""
        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())

    async def initial_sync(self) -> None:
        """Perform a single sync to load initial state."""
        resp = await self._nio.sync(timeout=0, full_state=True)
        if isinstance(resp, SyncResponse):
            self._process_sync(resp)
        else:
            logger.warning("Initial sync error: %s", resp)

    @property
    def rooms(self) -> dict[str, Room]:
        return self._rooms

    async def send_message(self, room_id: str, body: str) -> str | None:
        """Send a text message. Returns event_id on success."""
        resp = await self._nio.room_send(
            room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": body},
        )
        if hasattr(resp, "event_id"):
            return resp.event_id
        logger.error("Send failed: %s", resp)
        return None

    async def send_reaction(self, room_id: str, event_id: str, key: str) -> str | None:
        """Send an m.reaction event."""
        resp = await self._nio.room_send(
            room_id,
            message_type="m.reaction",
            content={
                "m.relates_to": {
                    "rel_type": "m.annotation",
                    "event_id": event_id,
                    "key": key,
                }
            },
        )
        if hasattr(resp, "event_id"):
            return resp.event_id
        logger.error("Reaction send failed: %s", resp)
        return None

    async def send_typing(self, room_id: str, typing: bool, timeout: int = 4000) -> None:
        """Send typing notification."""
        await self._nio.room_typing(room_id, typing_state=typing, timeout=timeout)

    async def send_read_receipt(self, room_id: str, event_id: str) -> None:
        """Mark event as read."""
        await self._nio.room_read_markers(room_id, fully_read_event=event_id, read_event=event_id)

    async def redact_message(self, room_id: str, event_id: str, reason: str = "") -> None:
        """Redact (delete) a message."""
        await self._nio.room_redact(room_id, event_id, reason=reason or None)

    async def edit_message(self, room_id: str, event_id: str, new_body: str) -> str | None:
        """Edit an existing message."""
        resp = await self._nio.room_send(
            room_id,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": f"* {new_body}",
                "m.new_content": {"msgtype": "m.text", "body": new_body},
                "m.relates_to": {"rel_type": "m.replace", "event_id": event_id},
            },
        )
        if hasattr(resp, "event_id"):
            return resp.event_id
        return None

    async def load_more_messages(self, room_id: str, limit: int = 20) -> list[Message]:
        """Fetch older messages for a room via /messages."""
        nio_room = self._nio.rooms.get(room_id)
        if nio_room is None:
            return []
        start_token = getattr(nio_room, "prev_batch", None)
        if not start_token:
            return []
        resp = await self._nio.room_messages(
            room_id,
            start=start_token,
            limit=limit,
            direction="b",
        )
        if not isinstance(resp, RoomMessagesResponse):
            return []
        msgs = []
        for ev in resp.chunk:
            if isinstance(ev, RoomMessageText):
                msg = self._nio_event_to_message(ev)
                if msg:
                    msgs.append(msg)
        # Update prev_batch
        if resp.end:
            nio_room.prev_batch = resp.end
        return list(reversed(msgs))

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_room_update(self, cb: RoomUpdateCallback) -> None:
        self._on_room_update.append(cb)

    def on_message(self, cb: MessageCallback) -> None:
        self._on_message.append(cb)

    def on_typing(self, cb: TypingCallback) -> None:
        self._on_typing.append(cb)

    def on_read_receipt(self, cb: ReadReceiptCallback) -> None:
        self._on_read_receipt.append(cb)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_callbacks(self) -> None:
        self._nio.add_event_callback(self._on_room_message, RoomMessage)
        self._nio.add_event_callback(self._on_reaction_event, ReactionEvent)
        self._nio.add_event_callback(self._on_redaction_event, RedactionEvent)
        self._nio.add_event_callback(self._on_member_event, RoomMemberEvent)
        self._nio.add_response_callback(self._on_sync_response, SyncResponse)

    async def _sync_loop(self) -> None:
        """Continuous sync loop with reconnect logic."""
        backoff = 1.0
        while self._running:
            try:
                resp = await self._nio.sync(timeout=30_000, full_state=False)
                if isinstance(resp, SyncResponse):
                    self._process_sync(resp)
                    backoff = 1.0
                elif isinstance(resp, SyncError):
                    logger.warning("Sync error: %s — retrying in %ss", resp, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Sync exception: %s — retrying in %ss", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    def _process_sync(self, resp: SyncResponse) -> None:
        """Extract rooms and typing from a SyncResponse."""
        # Build/update room objects from nio state
        for room_id, nio_room in self._nio.rooms.items():
            room = self._rooms.get(room_id)
            if room is None:
                room = Room(
                    room_id=room_id,
                    display_name=nio_room.display_name or room_id,
                )
                self._rooms[room_id] = room
            else:
                room.display_name = nio_room.display_name or room_id

            # Update members
            room.members = list(nio_room.users.keys())

        # Process typing notifications from sync response rooms
        for room_id, room_info in resp.rooms.join.items():
            room = self._rooms.get(room_id)
            if room is None:
                continue
            for ev in room_info.ephemeral:
                if isinstance(ev, TypingNoticeEvent):
                    room.typing_users = ev.users
                    for cb in self._on_typing:
                        cb(room_id, ev.users)

            # Process read receipts from ephemeral
            for ev in room_info.ephemeral:
                self._process_read_receipt_event(room_id, ev)

        # Notify listeners for all rooms
        for room_id, room in self._rooms.items():
            for cb in self._on_room_update:
                cb(room_id, room)

    def _process_read_receipt_event(self, room_id: str, ev: Any) -> None:
        """Handle m.receipt ephemeral events (nio ReceiptEvent with list of Receipt)."""
        if not hasattr(ev, "receipts"):
            return
        for receipt in ev.receipts:
            if getattr(receipt, "receipt_type", None) in ("m.read", "m.read.private"):
                for cb in self._on_read_receipt:
                    cb(room_id, receipt.user_id, receipt.event_id)

    async def _on_sync_response(self, resp: SyncResponse) -> None:
        pass  # handled in _process_sync

    async def _on_room_message(self, room: MatrixRoom, event: RoomMessage) -> None:
        msg = self._nio_event_to_message(event)
        if msg is None:
            return
        room_obj = self._get_or_create_room(room)

        # Check if this is an edit (m.replace relation)
        relates_to = getattr(event, "source", {}).get("content", {}).get("m.relates_to", {})
        if relates_to.get("rel_type") == "m.replace":
            original_id = relates_to.get("event_id")
            for existing in room_obj.messages:
                if existing.event_id == original_id:
                    new_content = (
                        getattr(event, "source", {})
                        .get("content", {})
                        .get("m.new_content", {})
                    )
                    existing.edited_body = new_content.get("body", msg.body)
                    for cb in self._on_message:
                        cb(room.room_id, existing)
                    return
        else:
            room_obj.messages.append(msg)
            for cb in self._on_message:
                cb(room.room_id, msg)

    async def _on_reaction_event(self, room: MatrixRoom, event: ReactionEvent) -> None:
        room_obj = self._get_or_create_room(room)
        relates_to = event.reacts_to
        key = event.key
        # Find target message
        for msg in room_obj.messages:
            if msg.event_id == relates_to:
                if key not in msg.reactions:
                    msg.reactions[key] = []
                if event.sender not in msg.reactions[key]:
                    msg.reactions[key].append(event.sender)
                break
        for cb in self._on_room_update:
            cb(room.room_id, room_obj)

    async def _on_redaction_event(self, room: MatrixRoom, event: RedactionEvent) -> None:
        room_obj = self._get_or_create_room(room)
        for msg in room_obj.messages:
            if msg.event_id == event.redacts:
                msg.redacted = True
                msg.body = "[Message deleted]"
                break
        for cb in self._on_room_update:
            cb(room.room_id, room_obj)

    async def _on_member_event(self, room: MatrixRoom, event: RoomMemberEvent) -> None:
        room_obj = self._get_or_create_room(room)
        room_obj.members = list(room.users.keys())
        for cb in self._on_room_update:
            cb(room.room_id, room_obj)

    async def _on_key_verification(self, event: KeyVerificationEvent) -> None:
        pass  # future: key verification UI

    def _get_or_create_room(self, nio_room: MatrixRoom) -> Room:
        if nio_room.room_id not in self._rooms:
            self._rooms[nio_room.room_id] = Room(
                room_id=nio_room.room_id,
                display_name=nio_room.display_name or nio_room.room_id,
                members=list(nio_room.users.keys()),
            )
        return self._rooms[nio_room.room_id]

    def _nio_event_to_message(self, event: RoomMessage) -> Message | None:
        body = getattr(event, "body", "")
        if not body:
            return None
        return Message(
            event_id=event.event_id,
            sender=event.sender,
            body=body,
            timestamp=event.server_timestamp,
            msgtype=getattr(event, "msgtype", "m.text"),
        )
