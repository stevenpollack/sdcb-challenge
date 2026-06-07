"""Entry point."""
import logging
import sys

from .app import MatrixApp
from .client import MatrixClient
from .config import Config
from .session import load_session


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        cfg = Config.from_env()
    except KeyError as exc:
        print(f"Missing environment variable: {exc}", file=sys.stderr)
        print("Copy .env.local.example to .env.local and fill in credentials.", file=sys.stderr)
        sys.exit(1)

    client = MatrixClient(cfg.homeserver, cfg.user_id)

    # Try to restore a previous session to avoid re-login
    saved = load_session()
    if saved and saved.get("user_id") == cfg.user_id:
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            client.restore_session(saved["access_token"], saved.get("device_id", ""))
        )

    app = MatrixApp(client)
    app.run()


if __name__ == "__main__":
    main()
