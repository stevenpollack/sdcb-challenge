"""Tests for configuration loading."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from matrixtui.config import load_config, _load_dotenv


def test_load_dotenv_parses_key_value(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("MATRIX_HOMESERVER=https://test.example.com\nMATRIX_USER=@bob:test.example.com\n")
    with patch.dict(os.environ, {}, clear=True):
        _load_dotenv(env_file)
        assert os.environ["MATRIX_HOMESERVER"] == "https://test.example.com"
        assert os.environ["MATRIX_USER"] == "@bob:test.example.com"


def test_load_dotenv_skips_comments(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("# this is a comment\nMATRIX_PASSWORD=secret\n")
    with patch.dict(os.environ, {}, clear=True):
        _load_dotenv(env_file)
        assert os.environ.get("MATRIX_PASSWORD") == "secret"
        assert "# this is a comment" not in os.environ


def test_load_dotenv_strips_quotes(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text('MATRIX_PASSWORD="quoted"\n')
    with patch.dict(os.environ, {}, clear=True):
        _load_dotenv(env_file)
        assert os.environ["MATRIX_PASSWORD"] == "quoted"


def test_load_dotenv_does_not_overwrite_existing(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("MATRIX_USER=@new:example.com\n")
    with patch.dict(os.environ, {"MATRIX_USER": "@existing:example.com"}):
        _load_dotenv(env_file)
        assert os.environ["MATRIX_USER"] == "@existing:example.com"


def test_load_dotenv_missing_file(tmp_path):
    # Should not raise
    _load_dotenv(tmp_path / "nonexistent.env")


def test_load_config_returns_dict():
    with patch.dict(os.environ, {
        "MATRIX_HOMESERVER": "https://hs.example.com",
        "MATRIX_USER": "@alice:example.com",
        "MATRIX_PASSWORD": "pass",
    }):
        cfg = load_config()
    assert cfg["homeserver"] == "https://hs.example.com"
    assert cfg["user"] == "@alice:example.com"
    assert cfg["password"] == "pass"


def test_load_config_defaults():
    """Verify defaults when no env vars are set (clears Matrix-specific vars)."""
    import tempfile
    matrix_keys = ["MATRIX_HOMESERVER", "MATRIX_USER", "MATRIX_PASSWORD"]
    saved = {k: os.environ.pop(k, None) for k in matrix_keys}
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                cfg = load_config()
            finally:
                os.chdir(original_cwd)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    assert cfg["homeserver"] == "https://matrix.org"
    assert cfg["user"] == ""
    assert cfg["password"] == ""
