"""Entry point for the Matrix TUI client."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from .app import MatrixApp
from .client import MatrixClient
from .config import AppConfig


def _setup_logging() -> None:
    log_path = Path("matrix-tui.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, mode="a")],
    )


def main() -> None:
    _setup_logging()
    try:
        config = AppConfig.from_env()
    except RuntimeError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("Ensure .env.local is present with MATRIX_HOMESERVER, MATRIX_USER, MATRIX_PASSWORD", file=sys.stderr)
        sys.exit(1)

    client = MatrixClient(config.homeserver, config.user_id)

    async def _run() -> None:
        await client.login(config.password)
        app = MatrixApp(client, config)
        await app.run_async()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
