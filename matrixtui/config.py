"""Load configuration from environment / .env.local."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local from repo root (two levels up from this file)
_root = Path(__file__).parent.parent
load_dotenv(_root / ".env.local")


@dataclass
class Config:
    homeserver: str
    user_id: str
    password: str

    @classmethod
    def from_env(cls) -> "Config":
        homeserver = os.environ.get("MATRIX_HOMESERVER", "https://matrix.org")
        user_id = os.environ["MATRIX_USER"]
        password = os.environ["MATRIX_PASSWORD"]
        return cls(homeserver=homeserver, user_id=user_id, password=password)
