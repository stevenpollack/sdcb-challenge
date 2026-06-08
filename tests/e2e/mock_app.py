"""Standalone script: runs MatrixApp with pre-seeded mock data.

textual-serve launches this as a subprocess when a browser connects.
No real Matrix homeserver is contacted.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from matrixtui.app import MatrixApp
from matrixtui.client import MatrixClient, Message, RoomSummary


def _build_mock_client() -> MatrixClient:
    with patch("matrixtui.client.AsyncClient"):
        client = MatrixClient("https://matrix.org", "@testuser:matrix.org")

    client.user_id = "@testuser:matrix.org"

    client.rooms = {
        "!general:m.org": RoomSummary(
            "!general:m.org",
            "General",
            unread_count=2,
            last_ts=3000,
            member_count=10,
        ),
        "!project:m.org": RoomSummary(
            "!project:m.org",
            "Project Alpha",
            unread_count=0,
            last_ts=2000,
            member_count=4,
        ),
        "!random:m.org": RoomSummary(
            "!random:m.org",
            "Random",
            unread_count=0,
            last_ts=1000,
            member_count=20,
        ),
    }

    client.messages = {
        "!general:m.org": [
            Message("$1", "@alice:m.org", "Hello everyone!", 1699000000000),
            Message("$2", "@bob:m.org", "Hey there", 1699000010000),
            Message(
                "$3",
                "@testuser:matrix.org",
                "Hi team",
                1699000020000,
                is_me=True,
            ),
        ],
        "!project:m.org": [
            Message("$4", "@alice:m.org", "Sprint planning tomorrow", 1699000005000),
        ],
        "!random:m.org": [
            Message(
                "$5",
                "@carol:m.org",
                "hey testuser check this out",
                1699000015000,
                mentions_me=True,
            ),
        ],
    }

    client._client.rooms = {
        "!general:m.org": MagicMock(users={}, topic="General discussion"),
        "!project:m.org": MagicMock(users={}, topic="Project Alpha planning"),
        "!random:m.org": MagicMock(users={}, topic=None),
    }

    # Stub out all methods that would hit the network.
    client.login = AsyncMock()
    client.start_sync = AsyncMock()
    client.logout = AsyncMock()
    client.send_message = AsyncMock(return_value="$sent")
    client.send_emote = AsyncMock(return_value="$emote")
    client.send_reaction = AsyncMock(return_value="$react")
    client.join_room = AsyncMock(return_value=None)
    client.leave_room = AsyncMock(return_value=False)
    client.invite_user = AsyncMock(return_value=False)
    client.kick_user = AsyncMock(return_value=False)
    client.ban_user = AsyncMock(return_value=False)
    client.unban_user = AsyncMock(return_value=False)
    client.set_display_name = AsyncMock(return_value=False)
    client.set_presence = AsyncMock(return_value=False)
    client.set_avatar = AsyncMock(return_value=False)
    client.create_room = AsyncMock(return_value=None)
    client.create_direct_message = AsyncMock(return_value=None)
    client.forget_room = AsyncMock(return_value=False)
    client.rename_room = AsyncMock(return_value=False)
    client.set_room_topic = AsyncMock(return_value=False)
    client.set_room_alias = AsyncMock(return_value=False)
    client.get_user_profile = AsyncMock(return_value=None)
    client.get_own_profile = AsyncMock(
        return_value={"display_name": "Test User", "avatar_url": None}
    )
    client.get_joined_members = AsyncMock(return_value=None)
    client.load_history = AsyncMock(return_value=[])
    client.send_read_receipt = AsyncMock()
    client.resolve_alias = AsyncMock(return_value=None)
    client.get_presence = AsyncMock(return_value=None)
    client.get_room_topic = MagicMock(return_value=None)
    client.get_room_members = MagicMock(return_value=[])
    client.mxc_to_http = MagicMock(return_value=None)
    client.can_send_message = MagicMock(return_value=True)
    client.get_user_power_level = MagicMock(return_value=None)
    client.total_unread = MagicMock(return_value=2)
    client.get_stats = MagicMock(
        return_value={
            "rooms": 3,
            "messages": 5,
            "pending_invites": 0,
            "typing_rooms": 0,
        }
    )
    client.search_messages = MagicMock(return_value=[])

    return client


def main() -> None:
    client = _build_mock_client()
    app = MatrixApp(client)

    async def fake_connect() -> None:
        app.query_one("#status-bar").update(
            f"Connected as {client.user_id} [2 unread]"
        )
        app._rebuild_room_list()

    app._connect = fake_connect
    app.run()


if __name__ == "__main__":
    main()
