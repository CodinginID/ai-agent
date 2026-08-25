# app/adapters/circuit_breaker.py
"""Circuit breaker pattern untuk mencegah cascade failure ke provider AI.

State machine:
  CLOSED    → normal, request diteruskan, kegagalan dicatat
  OPEN      → request langsung dilempar OpenStateError tanpa memanggil provider
  HALF_OPEN → satu request percobaan; sukses → CLOSED, gagal → OPEN lagi
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from app.ports.ai_provider import AIProvider


class OpenStateError(RuntimeError):
    """Raised when calling a provider whose circuit is open."""


class CircuitBreaker:
    """Circuit breaker yang membalut satu provider.

    ``name`` dipakai untuk metric/logging. ``threshold`` adalah jumlah kegagalan
    berturut-turut sebelum state berubah ke OPEN. ``timeout`` (detik) adalah
    waktu menunggu sebelum mencoba HALF_OPEN.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, name: str, threshold: int = 3, timeout: int = 60) -> None:
        self.name: str = name
        self.threshold: int = threshold
        self.timeout: int = timeout

        self.state: str = self.CLOSED
        self.failure_count: int = 0
        self.last_failure: datetime | None = None

        self._provider: AIProvider | None = None
        self._call_count_in_half_open: int = 0
        self._max_calls_in_half_open: int = 1

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """Provider tersedia (closed atau half_open)."""
        return self.state in (self.CLOSED, self.HALF_OPEN)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Snapshot metric sederhana untuk monitoring."""
        return {
            "circuit_name": self.name,
            "circuit_state": self.state,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
        }

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def record_success(self) -> None:
        """Reset failure counter dan kembali ke CLOSED."""
        self.failure_count = 0
        self.last_failure = None
        self.state = self.CLOSED
        self._call_count_in_half_open = 0

    def record_failure(self) -> None:
        """Catat kegagalan; bisa memicu transisi ke OPEN."""
        self.failure_count += 1
        self.last_failure = datetime.now()
        if self.failure_count >= self.threshold:
            self.state = self.OPEN

    def _check_timeout(self) -> None:
        """Jika OPEN dan timeout sudah lewat, transisi ke HALF_OPEN."""
        if self.state != self.OPEN or self.last_failure is None:
            return
        if datetime.now() - self.last_failure >= timedelta(seconds=self.timeout):
            self.state = self.HALF_OPEN
            self._call_count_in_half_open = 0

    # ------------------------------------------------------------------
    # Decorator-style call
    # ------------------------------------------------------------------

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Eksekusi ``func(*args, **kwargs)`` dengan proteksi circuit breaker.

        Jika circuit OPEN, langsung melempar ``OpenStateError``.
        Jika HALF_OPEN, izinkan satu percobaan; sukses → CLOSED, gagal → OPEN.
        """
        self._check_timeout()

        if self.state == self.OPEN:
            raise OpenStateError(
                f"Circuit '{self.name}' is open; provider unavailable. "
                f"Failures: {self.failure_count}, last: {self.last_failure}"
            )

        try:
            result = func(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result

    # ------------------------------------------------------------------
    # AIProvider adapter
    # ------------------------------------------------------------------

    def __init_subclass__(cls, **kwargs: Any) -> None:
        pass  # keep constructor signature flexible

    def wrap_provider(self, provider: AIProvider) -> _CircuitBreakerProvider:
        """Wrap AIProvider sehingga chat/chat_stream melewati circuit."""
        return _CircuitBreakerProvider(self, provider)


class _CircuitBreakerProvider:
    """AIProvider wrapper: meneruskan chat/chat_stream ke circuit breaker.

    Ini satu-satunya bridge antara CircuitBreaker dan protokol AIProvider,
    jadi API public provider tidak berubah bagi caller.
    """

    def __init__(self, breaker: CircuitBreaker, inner: AIProvider) -> None:
        self._breaker = breaker
        self._inner = inner

    def chat(self, prompt: str) -> str:
        return cast("str", self._breaker.call(self._inner.chat, prompt))

    def chat_stream(self, prompt: str) -> Iterator[str]:
        def _stream() -> Iterator[str]:
            yield from self._breaker.call(self._inner.chat_stream, prompt)
        return _stream()
