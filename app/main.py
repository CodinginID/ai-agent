from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn
from alembic import command as alembic_cmd
from alembic.config import Config

from app.config import BASE_DIR, settings
from app.interfaces.gateway import app as gateway_app
from app.setup.wizard import needs_setup, run_setup_wizard


def _is_dev() -> bool:
    return os.getenv("DEV", "").lower() in {"1", "true"}


def _setup_file_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "server.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    logging.getLogger().addHandler(handler)


def _run_migrations() -> None:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    logging.getLogger("alembic").setLevel(logging.WARNING)
    alembic_cmd.upgrade(cfg, "head")


def main() -> None:
    # First-run: no token → interactive setup wizard
    if needs_setup(settings.telegram_bot_token):
        if not sys.stdin.isatty():
            print(
                "ERROR: TELEGRAM_BOT_TOKEN belum diisi.\n"
                "Set env var atau isi .env sebelum menjalankan bot.",
                file=sys.stderr,
            )
            sys.exit(1)
        run_setup_wizard(BASE_DIR / ".env")
        # wizard exits after saving .env — user reruns make dev

    _run_migrations()
    _setup_file_logging(BASE_DIR / "data")

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
