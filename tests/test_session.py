"""Tests for session persistence (save/load/clear)."""
import json
from unittest.mock import MagicMock

import pytest

from matrixtui.session import clear_session, load_session, save_session


@pytest.fixture
def tmp_session(tmp_path, monkeypatch):
    """Redirect _SESSION_FILE to a temp path for isolation."""
    session_file = tmp_path / "session.json"
    import matrixtui.session as mod
    monkeypatch.setattr(mod, "_SESSION_FILE", session_file)
    return session_file


def test_save_and_load_roundtrip(tmp_session):
    save_session("https://matrix.org", "@test:matrix.org", "tok123", "dev1")
    data = load_session()
    assert data is not None
    assert data["homeserver"] == "https://matrix.org"
    assert data["user_id"] == "@test:matrix.org"
    assert data["access_token"] == "tok123"
    assert data["device_id"] == "dev1"


def test_save_creates_parent_dirs(tmp_path, monkeypatch):
    deep = tmp_path / "a" / "b" / "session.json"
    import matrixtui.session as mod
    monkeypatch.setattr(mod, "_SESSION_FILE", deep)
    save_session("https://matrix.org", "@a:m.org", "tok", "dev")
    assert deep.exists()


def test_save_sets_permissions(tmp_session):
    save_session("https://matrix.org", "@a:m.org", "tok", "dev")
    mode = tmp_session.stat().st_mode & 0o777
    assert mode == 0o600


def test_load_returns_none_when_missing(tmp_session):
    assert load_session() is None


def test_load_returns_none_for_invalid_json(tmp_session):
    tmp_session.parent.mkdir(parents=True, exist_ok=True)
    tmp_session.write_text("not json")
    assert load_session() is None


def test_load_returns_none_for_missing_keys(tmp_session):
    tmp_session.parent.mkdir(parents=True, exist_ok=True)
    tmp_session.write_text(json.dumps({"homeserver": "x"}))
    assert load_session() is None


def test_clear_removes_file(tmp_session):
    save_session("https://matrix.org", "@a:m.org", "tok", "dev")
    assert tmp_session.exists()
    clear_session()
    assert not tmp_session.exists()


def test_clear_noop_when_no_file(tmp_session):
    # Should not raise
    clear_session()


def test_clear_swallows_exceptions(tmp_session, monkeypatch):
    import matrixtui.session as mod
    mock_file = MagicMock(unlink=MagicMock(side_effect=PermissionError("denied")))
    monkeypatch.setattr(mod, "_SESSION_FILE", mock_file)
    # Should not raise
    clear_session()
