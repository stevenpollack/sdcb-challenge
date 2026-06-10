"""Unit tests for the Matrix client data models and helpers."""
from __future__ import annotations

import pytest
from matrixclient.client import Message, Room


class TestMessageModel:
    def test_default_fields(self):
        msg = Message(
            event_id="$abc123",
            sender="@alice:matrix.org",
            body="Hello",
            timestamp=1_700_000_000_000,
        )
        assert msg.event_id == "$abc123"
        assert msg.sender == "@alice:matrix.org"
        assert msg.body == "Hello"
        assert msg.msgtype == "m.text"
        assert msg.edited_body is None
        assert msg.reactions == {}
        assert msg.redacted is False

    def test_reactions_independent(self):
        m1 = Message("$e1", "@a:h", "hi", 0)
        m2 = Message("$e2", "@b:h", "hey", 0)
        m1.reactions["👍"] = ["@a:h"]
        assert "👍" not in m2.reactions

    def test_redacted_message(self):
        msg = Message("$e", "@a:h", "[Message deleted]", 0, redacted=True)
        assert msg.redacted is True


class TestRoomModel:
    def test_default_fields(self):
        room = Room(room_id="!abc:matrix.org", display_name="Test Room")
        assert room.members == []
        assert room.messages == []
        assert room.unread_count == 0
        assert room.typing_users == []
        assert room.last_read_event_id is None

    def test_messages_independent(self):
        r1 = Room("!r1:h", "R1")
        r2 = Room("!r2:h", "R2")
        r1.messages.append(Message("$e1", "@a:h", "hi", 0))
        assert len(r2.messages) == 0
