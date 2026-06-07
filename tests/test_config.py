"""Tests for config loading."""
import os
import pytest
from unittest.mock import patch

from matrixtui.config import Config


def test_config_from_env():
    env = {
        "MATRIX_HOMESERVER": "https://example.org",
        "MATRIX_USER": "@test:example.org",
        "MATRIX_PASSWORD": "secret",
    }
    with patch.dict(os.environ, env):
        cfg = Config.from_env()
    assert cfg.homeserver == "https://example.org"
    assert cfg.user_id == "@test:example.org"
    assert cfg.password == "secret"


def test_config_default_homeserver():
    env = {
        "MATRIX_USER": "@test:matrix.org",
        "MATRIX_PASSWORD": "pw",
    }
    with patch.dict(os.environ, env, clear=False):
        env_no_hs = {k: v for k, v in os.environ.items() if k != "MATRIX_HOMESERVER"}
        env_no_hs.update(env)
        with patch.dict(os.environ, env_no_hs, clear=True):
            cfg = Config.from_env()
    assert cfg.homeserver == "https://matrix.org"


def test_config_missing_user_raises():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(KeyError):
            Config.from_env()
