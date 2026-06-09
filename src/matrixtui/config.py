"""Configuration loader from environment / .env.local."""

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env parser — no dependencies required."""
    if not path.exists():
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def load_config() -> dict:
    """Return config dict, loading .env.local if present."""
    # Walk up from cwd to find .env.local (max 3 levels)
    here = Path.cwd()
    for candidate in [here, here.parent, here.parent.parent]:
        env_file = candidate / ".env.local"
        if env_file.exists():
            _load_dotenv(env_file)
            break

    return {
        "homeserver": os.environ.get("MATRIX_HOMESERVER", "https://matrix.org"),
        "user": os.environ.get("MATRIX_USER", ""),
        "password": os.environ.get("MATRIX_PASSWORD", ""),
    }
