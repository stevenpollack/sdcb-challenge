"""Shared fixtures and helpers for the test suite."""

import os
from pathlib import Path


def pytest_configure(config):
    """Load .env.local once, before any test runs."""
    repo_root = Path(__file__).parent.parent
    env_file = repo_root / ".env.local"
    if env_file.exists():
        with open(env_file) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v


def live_credentials() -> dict | None:
    """Return credentials dict if .env.local is present and populated, else None."""
    hs = os.environ.get("MATRIX_HOMESERVER")
    user = os.environ.get("MATRIX_USER")
    pw = os.environ.get("MATRIX_PASSWORD")
    if hs and user and pw:
        return {"homeserver": hs, "user": user, "password": pw}
    return None
