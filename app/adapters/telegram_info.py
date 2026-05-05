"""Helper untuk fetch bot info dari Telegram API.

Username bot di-derive dari ``TELEGRAM_BOT_TOKEN`` lewat ``getMe`` — supaya
user tidak perlu set env var terpisah. Hasil di-cache satu kali per proses.
"""

from __future__ import annotations

import asyncio
from threading import Lock

import httpx

from app.config import settings

_cache_lock = Lock()
_cached_username: str | None = None


def _telegram_api(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


async def get_bot_username() -> str | None:
    """Fetch username bot via getMe. None kalau token kosong/error."""
    global _cached_username
    with _cache_lock:
        if _cached_username:
            return _cached_username

    if not settings.telegram_bot_token:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.get(_telegram_api("getMe"))
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("ok"):
            return None
        username = str(data["result"].get("username", "")).lstrip("@")
    except httpx.HTTPError:
        return None

    if not username:
        return None

    with _cache_lock:
        _cached_username = username
    return username


def get_bot_username_sync() -> str | None:
    """Wrapper sync untuk caller di luar context async."""
    try:
        return asyncio.run(get_bot_username())
    except RuntimeError:
        # Sudah di dalam event loop — caller harus pakai versi async.
        return None


def clear_cache() -> None:
    """Untuk test — reset cache supaya next call hit API lagi."""
    global _cached_username
    with _cache_lock:
        _cached_username = None
