"""Configuration loader from environment / .env.local."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    # Try project root .env.local first, then .env
    for name in (".env.local", ".env"):
        p = Path(__file__).parents[2] / name
        if p.exists():
            load_dotenv(p, override=True)
            return
    load_dotenv(override=True)


_load_env()


@dataclass(frozen=True)
class AppConfig:
    homeserver: str
    user_id: str
    password: str
    homeserver_b: str
    user_id_b: str
    password_b: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        def req(key: str) -> str:
            val = os.environ.get(key, "")
            if not val:
                raise RuntimeError(f"Missing required env var: {key}")
            return val

        return cls(
            homeserver=req("MATRIX_HOMESERVER"),
            user_id=req("MATRIX_USER"),
            password=req("MATRIX_PASSWORD"),
            homeserver_b=os.environ.get("MATRIX_HOMESERVER_B", req("MATRIX_HOMESERVER")),
            user_id_b=req("MATRIX_USER_B"),
            password_b=req("MATRIX_PASSWORD_B"),
        )
