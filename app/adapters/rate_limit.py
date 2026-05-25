"""RedisRateLimiter — per-user cooldown via Redis ``SET NX EX``.

Tujuan: cegah satu user spam request ke pipeline AI yang resource-bound
(Ollama lokal). Pakai sync client supaya bisa dipanggil dari sync generator
``HandleMessageUseCase.handle()`` tanpa overhead bridge event loop.

Key format: ``ratelimit:{user_id}`` dengan TTL = cooldown.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """Cooldown per user_id. ``is_allowed`` mengembalikan True kalau request boleh lewat."""

    def __init__(self, redis_client: Any, cooldown_seconds: int) -> None:
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        self._client = redis_client
        self._cooldown = cooldown_seconds

    def is_allowed(self, user_id: str) -> bool:
        # cooldown_seconds <= 0 → fitur efektif off.
        if self._cooldown <= 0:
            return True
        key = _key(user_id)
        try:
            result = self._client.set(key, "1", ex=self._cooldown, nx=True)
        except Exception as exc:
            # Fail open: Redis down jangan blokir user.
            logger.warning("Rate limiter Redis SET failed for %s: %s", user_id, exc)
            return True
        return bool(result)


def _key(user_id: str) -> str:
    return f"ratelimit:{user_id}"
