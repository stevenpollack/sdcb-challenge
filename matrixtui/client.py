"""Async Matrix client wrapping matrix-nio."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable

from nio import (
    AsyncClient,
    AsyncClientConfig,
    LoginResponse,
    MatrixRoom,
    MessageDirection,
    RoomMessagesResponse,
    RoomMessageText,
    RoomNameEvent,
    RoomSendResponse,
    SyncResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class Message:
    event_id: str
    sender: str
    body: str
    timestamp: int  # milliseconds since epoch
    is_me: bool = False


@dataclass
class RoomSummary:
    room_id: str
    display_name: str
    unread_count: int = 0
    last_message: str = ""
    last_ts: int = 0
    members: list[str] = field(default_factory=list)


class MatrixClient:
    """Thin async wrapper around nio.AsyncClient."""

    def __init__(self, homeserver: str, user_id: str) -> None:
        config = AsyncClientConfig(max_limit_exceeded=0, max_timeouts=0)
        self._client = AsyncClient(homeserver, user_id, config=config)
        self.user_id = user_id
        self.rooms: dict[str, RoomSummary] = {}
        self.messages: dict[str, list[Message]] = {}
        self._sync_task: asyncio.Task | None = None
        self._on_room_update: list[Callable[[str], None]] = []
        self._on_message: list[Callable[[str, Message], None]] = []
        self._running = False

        self._client.add_event_callback(self._on_room_message, RoomMessageText)
        self._client.add_event_callback(self._on_room_name, RoomNameEvent)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self, password: str) -> None:
        resp = await self._client.login(password, device_name="matrixtui")
        if not isinstance(resp, LoginResponse):
            raise RuntimeError(f"Login failed: {resp}")
        logger.info("Logged in as %s", self.user_id)

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
        for room_id, room in self._client.rooms.items():
            summary = self.rooms.get(room_id)
            if summary is None:
                summary = RoomSummary(
                    room_id=room_id,
                    display_name=self._room_name(room),
                )
                self.rooms[room_id] = summary
                self.messages.setdefault(room_id, [])
            else:
                summary.display_name = self._room_name(room)
            summary.unread_count = room.unread_notifications

        # Process timeline events from sync response
        if hasattr(resp, "rooms") and resp.rooms:
            for room_id, room_info in resp.rooms.join.items():
                for event in room_info.timeline.events:
                    if isinstance(event, RoomMessageText):
                        msg = self._event_to_message(event)
                        msgs = self.messages.setdefault(room_id, [])
                        if not any(m.event_id == msg.event_id for m in msgs):
                            msgs.append(msg)
                            # Keep sorted by timestamp
                            msgs.sort(key=lambda m: m.timestamp)
                            summary = self.rooms.get(room_id)
                            if summary:
                                summary.last_message = msg.body[:80]
                                summary.last_ts = msg.timestamp
                            for cb in self._on_message:
                                cb(room_id, msg)
                            for cb in self._on_room_update:
                                cb(room_id)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    async def _on_room_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
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

    async def load_history(self, room_id: str, limit: int = 50) -> list[Message]:
        """Load older messages for a room via /messages."""
        resp = await self._client.room_messages(
            room_id,
            start=self._client.rooms[room_id].prev_batch if room_id in self._client.rooms else "",
            limit=limit,
            direction=MessageDirection.back,
        )
        if not isinstance(resp, RoomMessagesResponse):
            return []
        msgs: list[Message] = []
        for event in resp.chunk:
            if isinstance(event, RoomMessageText):
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

    def _event_to_message(self, event: RoomMessageText) -> Message:
        return Message(
            event_id=event.event_id,
            sender=event.sender,
            body=event.body,
            timestamp=event.server_timestamp,
            is_me=(event.sender == self.user_id),
        )

    @staticmethod
    def _room_name(room: MatrixRoom) -> str:
        if room.display_name:
            return room.display_name
        if room.name:
            return room.name
        members = [m for m in room.users if not m.endswith(":matrix.org") or True]
        non_self = [m for m in members if m != room.own_user_id]
        if non_self:
            user = room.users.get(non_self[0])
            if user and user.display_name:
                return user.display_name
            return non_self[0]
        return room.room_id

    def on_room_update(self, cb: Callable[[str], None]) -> None:
        self._on_room_update.append(cb)

    def on_message(self, cb: Callable[[str, Message], None]) -> None:
        self._on_message.append(cb)

    @property
    def nio_client(self) -> AsyncClient:
        return self._client
