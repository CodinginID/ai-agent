from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path

import uvicorn
from alembic import command as alembic_cmd
from alembic.config import Config

from app.adapters.logger import json_logger, setup_json_logging
from app.config import BASE_DIR, settings
from app.interfaces.gateway import app as gateway_app

logger = json_logger(__name__)


def _is_dev() -> bool:
    return os.getenv("DEV", "").lower() in {"1", "true"}


def _setup_logging(log_dir: Path) -> None:
    setup_json_logging(log_dir)


def _run_migrations() -> None:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    logging.getLogger("alembic").setLevel(logging.WARNING)
    alembic_cmd.upgrade(cfg, "head")


def _handle_shutdown(signum: int, frame) -> None:
    """Handle SIGTERM and SIGINT signals for graceful shutdown."""
    logger.info("Shutting down...")
    # Exit with code 0 for graceful shutdown
    # uvicorn's built-in signal handling will trigger lifespan cleanup
    # (stop_pubsub_listener, close connections, etc.)
    sys.exit(0)


def main() -> None:
    _run_migrations()
    _setup_logging(BASE_DIR / "data")

    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # Backend selalu uvicorn — TUI client jalan terpisah via `python -m app.tui`.
    # `--reload` aktif kalau DEV=1 (proses lokal); container Docker tidak set DEV.
    if _is_dev():
        uvicorn.run(
            "app.interfaces.gateway:app",
            host="0.0.0.0",
            port=settings.port,
            reload=True,
            reload_dirs=["app"],
            log_level="info",
        )
    else:
        uvicorn.run(gateway_app, host="0.0.0.0", port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
