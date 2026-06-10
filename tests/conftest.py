"""Shared fixtures for Matrix TUI tests."""
from __future__ import annotations

import os
import asyncio
import pytest
from pathlib import Path
from dotenv import load_dotenv

# Load credentials from .env.local at project root
_root = Path(__file__).parents[1]
for _name in (".env.local", ".env"):
    _p = _root / _name
    if _p.exists():
        load_dotenv(_p, override=True)
        break


def _req(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        pytest.skip(f"Missing env var {key} — skipping integration test")
    return val


@pytest.fixture(scope="session")
def homeserver_url() -> str:
    return _req("MATRIX_HOMESERVER")


@pytest.fixture(scope="session")
def user_a_id() -> str:
    return _req("MATRIX_USER")


@pytest.fixture(scope="session")
def user_a_password() -> str:
    return _req("MATRIX_PASSWORD")


@pytest.fixture(scope="session")
def homeserver_b_url() -> str:
    return os.environ.get("MATRIX_HOMESERVER_B", _req("MATRIX_HOMESERVER"))


@pytest.fixture(scope="session")
def user_b_id() -> str:
    return _req("MATRIX_USER_B")


@pytest.fixture(scope="session")
def user_b_password() -> str:
    return _req("MATRIX_PASSWORD_B")
