"""Persist and restore Matrix login sessions to avoid re-login on every start."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_SESSION_FILE = Path.home() / ".config" / "matrixtui" / "session.json"


def save_session(homeserver: str, user_id: str, access_token: str, device_id: str) -> None:
    """Persist session credentials to disk."""
    _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "homeserver": homeserver,
        "user_id": user_id,
        "access_token": access_token,
        "device_id": device_id,
    }
    _SESSION_FILE.write_text(json.dumps(data, indent=2))
    _SESSION_FILE.chmod(0o600)
    logger.debug("Session saved to %s", _SESSION_FILE)


def load_session() -> dict | None:
    """Load a previously saved session. Returns None if not found or invalid."""
    if not _SESSION_FILE.exists():
        return None
    try:
        data = json.loads(_SESSION_FILE.read_text())
        required = {"homeserver", "user_id", "access_token", "device_id"}
        if not required.issubset(data):
            return None
        return data
    except Exception as exc:
        logger.warning("Failed to load session: %s", exc)
        return None


def clear_session() -> None:
    """Delete the saved session file."""
    try:
        _SESSION_FILE.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Failed to clear session: %s", exc)
