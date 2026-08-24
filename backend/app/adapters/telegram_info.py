"""Helper untuk info bot Telegram di sisi Core.

Core tidak lagi menyimpan TELEGRAM_BOT_TOKEN. Username bot dikonfigurasi
lewat TELEGRAM_BOT_USERNAME di .env — dipakai untuk generate deep link pairing.
"""

from __future__ import annotations

from app.config import settings


async def get_bot_username() -> str | None:
    """Return username bot dari config. None kalau belum dikonfigurasi."""
    return settings.telegram_bot_username or None


def get_bot_username_sync() -> str | None:
    return settings.telegram_bot_username or None


def clear_cache() -> None:
    pass
