"""Entry point."""
import asyncio
import logging
import sys

from .config import Config
from .client import MatrixClient
from .app import MatrixApp


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
    app = MatrixApp(client)
    app.run()


if __name__ == "__main__":
    main()
