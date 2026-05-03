from __future__ import annotations

import logging
import os
import sys

import uvicorn

from app.config import BASE_DIR, settings
from app.setup.wizard import needs_setup


def _is_dev() -> bool:
    return os.getenv("DEV", "").lower() in {"1", "true"}


def _run_migrations() -> None:
    from alembic import command as alembic_cmd
    from alembic.config import Config

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
        from app.setup.wizard import run_setup_wizard
        run_setup_wizard(BASE_DIR / ".env")
        # wizard exits after saving .env — user reruns make dev

    _run_migrations()

    mode = os.getenv("MODE", "polling").lower()
    dev = _is_dev()

    if mode == "webhook" or settings.enable_webhook:
        if dev:
            # Hot-reload: string import path required by uvicorn reload mode
            uvicorn.run(
                "app.interfaces.gateway:app",
                host="0.0.0.0",
                port=settings.port,
                reload=True,
                reload_dirs=["app"],
                log_level="info",
            )
        else:
            from app.interfaces.gateway import app as gateway_app
            uvicorn.run(gateway_app, host="0.0.0.0", port=settings.port, log_level="info")
    else:
        from app.bot import main as run_polling
        run_polling()


if __name__ == "__main__":
    main()
