"""Tests for __main__ entry point."""
from unittest.mock import MagicMock, patch

import pytest


def test_main_exits_on_missing_credentials(capsys):
    """main() prints an error and exits 1 when env vars are absent."""
    with patch.dict("os.environ", {}, clear=True):
        # Prevent dotenv from loading .env.local during test
        with patch("matrixtui.config.load_dotenv"):
            with pytest.raises(SystemExit) as exc_info:
                from matrixtui.__main__ import main
                main()
    assert exc_info.value.code == 1


def test_main_constructs_app_and_runs():
    """main() constructs MatrixClient + MatrixApp and calls app.run()."""
    env = {
        "MATRIX_HOMESERVER": "https://matrix.org",
        "MATRIX_USER": "@test:matrix.org",
        "MATRIX_PASSWORD": "pw",
    }
    mock_app = MagicMock()
    mock_app_cls = MagicMock(return_value=mock_app)
    mock_client_cls = MagicMock()

    with patch.dict("os.environ", env):
        with patch("matrixtui.config.load_dotenv"):
            with patch("matrixtui.__main__.MatrixApp", mock_app_cls):
                with patch("matrixtui.__main__.MatrixClient", mock_client_cls):
                    from matrixtui.__main__ import main
                    main()

    mock_app.run.assert_called_once()


def test_main_restores_session_when_available():
    """main() calls restore_session (now sync) when a saved session matches."""
    from matrixtui.__main__ import main

    env = {
        "MATRIX_HOMESERVER": "https://matrix.org",
        "MATRIX_USER": "@test:matrix.org",
        "MATRIX_PASSWORD": "pw",
    }
    saved = {
        "homeserver": "https://matrix.org",
        "user_id": "@test:matrix.org",
        "access_token": "tok_saved",
        "device_id": "DEV1",
    }
    mock_app = MagicMock()
    mock_client = MagicMock()
    mock_client_cls = MagicMock(return_value=mock_client)

    with patch.dict("os.environ", env):
        with patch("matrixtui.config.load_dotenv"):
            with patch("matrixtui.__main__.load_session", return_value=saved):
                with patch("matrixtui.__main__.MatrixApp", return_value=mock_app):
                    with patch("matrixtui.__main__.MatrixClient", mock_client_cls):
                        main()

    mock_client.restore_session.assert_called_once_with("tok_saved", "DEV1")
