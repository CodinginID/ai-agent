"""Retry helpers with exponential backoff + jitter.

Digunakan oleh adapter-layer (Ollama, Anthropic, GitHub, Telegram chat)
untuk menangani fluktuasi jaringan / rate-limit tanpa mengubah signature
class/func masing-masing adapter.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)


def _compute_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter: bool,
) -> float:
    """Hitung delay untuk attempt ke-``attempt`` (0-based).

    Backoff = ``base_delay * 2**attempt``, capped di ``max_delay``.
    Kalau ``jitter=True``, dikurangi acak di range ``[0, delay]`` agar
    client yang gagal bersamaan tidak semua retry tepat di waktu yang sama
    (thundering herd).
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay = random.uniform(0, delay)
    return float(delay)


def retry_with_backoff[T](
    func: Callable[..., T],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> Callable[..., T]:
    """Decorator / pembungkus untuk fungsi sinkron.

    Menangkap ``Exception`` (generic) pada setiap attempt, log ``WARNING``
    setiap kali retry, lalu coba lagi dengan delay eksponensial.
    Jika semua attempt gagal, exception terakhir dilempar ke caller.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt == max_retries:
                    break
                delay = _compute_delay(attempt, base_delay, max_delay, jitter)
                log.warning(
                    "retry %s attempt %d/%d gagal (%s), "
                    "menunggu %.2fs sebelum coba lagi",
                    func.__qualname__,
                    attempt + 1,
                    max_retries + 1,
                    exc,
                    delay,
                )
                import time

                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    return wrapper


async def retry_async[T](
    func: Callable[..., Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> T:
    """Async variant — sama seperti ``retry_with_backoff`` tapi pakai
    ``await`` + ``asyncio.sleep``.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as exc:
            last_exc = exc
            if attempt == max_retries:
                break
            delay = _compute_delay(attempt, base_delay, max_delay, jitter)
            log.warning(
                "retry_async %s attempt %d/%d gagal (%s), "
                "menunggu %.2fs sebelum coba lagi",
                func.__qualname__,
                attempt + 1,
                max_retries + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc
