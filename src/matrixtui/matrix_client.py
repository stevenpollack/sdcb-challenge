"""Thin async Matrix client wrapper around matrix-nio."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from nio import (
    AsyncClient,
    AsyncClientConfig,
    LoginResponse,
    MatrixRoom,
    RoomMessageText,
    RoomMemberEvent,
    SyncError,
    RoomSendResponse,
    JoinedRoomsResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class Message:
    room_id: str
    sender: str
    body: str
    event_id: str = ""
    timestamp: int = 0


@dataclass
class Room:
    room_id: str
    display_name: str
    member_count: int = 0


class MatrixClientError(Exception):
    pass


class MatrixClient:
    """Manages a single Matrix session with real-time sync."""

    def __init__(
        self,
        homeserver: str,
        user_id: str,
        password: str,
        on_message: Optional[Callable[[Message], None]] = None,
        on_room_update: Optional[Callable[[list[Room]], None]] = None,
    ) -> None:
        self.homeserver = homeserver
        self.user_id = user_id
        self.password = password
        self.on_message = on_message
        self.on_room_update = on_room_update

        config = AsyncClientConfig(max_limit_exceeded=0, max_timeouts=0)
        self._client = AsyncClient(homeserver, user_id, config=config)
        self._sync_task: Optional[asyncio.Task] = None
        self._connected = False
        self._rooms: dict[str, Room] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    async def login(self) -> None:
        """Login with retry on rate-limit (M_LIMIT_EXCEEDED)."""
        for attempt in range(3):
            resp = await self._client.login(self.password)
            if isinstance(resp, LoginResponse):
                self._connected = True
                logger.info("Logged in as %s", self.user_id)
                return
            err_str = str(resp)
            if "M_LIMIT_EXCEEDED" in err_str and attempt < 2:
                wait = (attempt + 1) * 10
                logger.warning("Login rate-limited, retrying in %ss", wait)
                await asyncio.sleep(wait)
                continue
            raise MatrixClientError(f"Login failed: {resp}")

    async def start_sync(self) -> None:
        """Register callbacks and start sync loop in background."""
        self._client.add_event_callback(self._on_room_message, RoomMessageText)
        self._client.add_event_callback(self._on_room_member, RoomMemberEvent)
        self._sync_task = asyncio.create_task(self._sync_forever())

    async def stop(self) -> None:
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        await self._client.close()
        self._connected = False

    async def _sync_forever(self) -> None:
        """Continuous sync loop with reconnect on transient errors."""
        backoff = 1.0
        while True:
            try:
                await self._client.sync_forever(
                    timeout=30000,
                    full_state=True,
                )
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Sync error: %s — retrying in %ss", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            else:
                backoff = 1.0

    async def _on_room_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        msg = Message(
            room_id=room.room_id,
            sender=event.sender,
            body=event.body,
            event_id=event.event_id,
            timestamp=getattr(event, "server_timestamp", 0),
        )
        await self._update_rooms()
        if self.on_message:
            self.on_message(msg)

    async def _on_room_member(self, room: MatrixRoom, event: RoomMemberEvent) -> None:
        await self._update_rooms()

    async def _update_rooms(self) -> None:
        rooms = []
        for rid, rdata in self._client.rooms.items():
            rooms.append(Room(
                room_id=rid,
                display_name=rdata.display_name or rid,
                member_count=rdata.member_count,
            ))
        self._rooms = {r.room_id: r for r in rooms}
        if self.on_room_update:
            self.on_room_update(list(self._rooms.values()))

    async def get_rooms(self) -> list[Room]:
        resp = await self._client.joined_rooms()
        if isinstance(resp, JoinedRoomsResponse):
            rooms = []
            for rid in resp.rooms:
                nio_room = self._client.rooms.get(rid)
                name = nio_room.display_name if nio_room else rid
                count = nio_room.member_count if nio_room else 0
                rooms.append(Room(room_id=rid, display_name=name, member_count=count))
            self._rooms = {r.room_id: r for r in rooms}
        return list(self._rooms.values())

    async def send_message(self, room_id: str, body: str) -> str:
        """Send a text message; return the event_id."""
        resp = await self._client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": body},
        )
        if isinstance(resp, RoomSendResponse):
            return resp.event_id
        raise MatrixClientError(f"Send failed: {resp}")

    async def join_room(self, room_id_or_alias: str) -> str:
        """Join a room by ID or alias; return the room_id."""
        resp = await self._client.join(room_id_or_alias)
        from nio import JoinResponse
        if isinstance(resp, JoinResponse):
            await self._update_rooms()
            return resp.room_id
        raise MatrixClientError(f"Join failed: {resp}")

    async def get_room_history(self, room_id: str, limit: int = 50) -> list[Message]:
        """Fetch recent messages from room history."""
        from nio import RoomMessagesResponse
        resp = await self._client.room_messages(room_id, start="", limit=limit)
        if not isinstance(resp, RoomMessagesResponse):
            return []
        messages = []
        for event in reversed(resp.chunk):
            if isinstance(event, RoomMessageText):
                messages.append(Message(
                    room_id=room_id,
                    sender=event.sender,
                    body=event.body,
                    event_id=event.event_id,
                    timestamp=getattr(event, "server_timestamp", 0),
                ))
        return messages

    def get_display_name(self, user_id: str) -> str:
        """Return short display name for a user."""
        return user_id.split(":")[0].lstrip("@")
