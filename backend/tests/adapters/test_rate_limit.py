"""Unit tests RedisRateLimiter — pakai in-memory fake (no real Redis)."""
from __future__ import annotations

import time
from typing import Any

from app.adapters.rate_limit import RedisRateLimiter


class _FakeRedis:
    """Minimal stand-in for ``redis.Redis`` that supports ``SET NX EX``.

    Cukup untuk perilaku rate limiter: simpan value + expiry (epoch seconds),
    ``set(..., nx=True)`` return truthy hanya kalau key tidak ada / sudah expired.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float | None]] = {}

    def set(self, name: str, value: Any, ex: int | None = None, nx: bool = False) -> bool | None:
        existing = self._store.get(name)
        now = time.time()
        if existing is not None:
            _, expiry = existing
            if expiry is not None and expiry <= now:
                del self._store[name]
                existing = None
        if nx and existing is not None:
            return None
        expiry = now + ex if ex is not None else None
        self._store[name] = (value, expiry)
        return True

    def expire_now(self, name: str) -> None:
        if name in self._store:
            val, _ = self._store[name]
            self._store[name] = (val, time.time() - 1)


def test_first_call_in_window_is_allowed() -> None:
    limiter = RedisRateLimiter(_FakeRedis(), cooldown_seconds=3)
    assert limiter.is_allowed("user-1") is True


def test_second_call_within_window_is_blocked() -> None:
    fake = _FakeRedis()
    limiter = RedisRateLimiter(fake, cooldown_seconds=3)
    assert limiter.is_allowed("user-1") is True
    assert limiter.is_allowed("user-1") is False


def test_call_after_window_is_allowed_again() -> None:
    fake = _FakeRedis()
    limiter = RedisRateLimiter(fake, cooldown_seconds=3)
    assert limiter.is_allowed("user-1") is True
    fake.expire_now("ratelimit:user-1")
    assert limiter.is_allowed("user-1") is True


def test_different_users_have_independent_windows() -> None:
    limiter = RedisRateLimiter(_FakeRedis(), cooldown_seconds=3)
    assert limiter.is_allowed("user-1") is True
    assert limiter.is_allowed("user-2") is True
    assert limiter.is_allowed("user-1") is False
    assert limiter.is_allowed("user-2") is False


def test_zero_cooldown_disables_limiter() -> None:
    fake = _FakeRedis()
    limiter = RedisRateLimiter(fake, cooldown_seconds=0)
    assert limiter.is_allowed("user-1") is True
    assert limiter.is_allowed("user-1") is True
    assert fake._store == {}


def test_redis_failure_fails_open() -> None:
    class _BoomRedis:
        def set(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("redis down")

    limiter = RedisRateLimiter(_BoomRedis(), cooldown_seconds=3)
    assert limiter.is_allowed("user-1") is True
