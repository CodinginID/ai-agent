# tests/adapters/test_circuit_breaker.py
"""Unit tests untuk CircuitBreaker pattern."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.adapters.circuit_breaker import CircuitBreaker, OpenStateError


# ---------------------------------------------------------------------------
# Helpers: make a fake AIProvider without importing the real SDK
# ---------------------------------------------------------------------------

class _FakeProvider:
    """Minimal mock that satisfies the AIProvider protocol."""

    def __init__(self, chat_side_effect: Exception | None = None) -> None:
        self.chat_calls: list[str] = []
        self.chat_stream_calls: list[str] = []
        self.chat_side_effect = chat_side_effect

    def chat(self, prompt: str) -> str:
        self.chat_calls.append(prompt)
        if self.chat_side_effect:
            raise self.chat_side_effect
        return f"reply:{prompt}"

    def chat_stream(self, prompt: str) -> Iterator[str]:
        self.chat_stream_calls.append(prompt)
        if self.chat_side_effect:
            raise self.chat_side_effect
        yield "hello"
        yield "world"


# ---------------------------------------------------------------------------
# State: CLOSED
# ---------------------------------------------------------------------------

def test_initial_state_is_closed() -> None:
    cb = CircuitBreaker("test")
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failure_count == 0
    assert cb.last_failure is None


def test_closed_allows_calls() -> None:
    cb = CircuitBreaker("test", threshold=3)
    provider = _FakeProvider()
    result = cb.call(provider.chat, "hi")
    assert result == "reply:hi"
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failure_count == 0


def test_closed_records_success_resets_counter() -> None:
    cb = CircuitBreaker("test", threshold=3)
    cb.failure_count = 2  # simulate prior failures
    cb.state = CircuitBreaker.CLOSED
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.last_failure is None


def test_closed_records_failure_increments_counter() -> None:
    cb = CircuitBreaker("test", threshold=3)
    cb.record_failure()
    assert cb.failure_count == 1
    assert cb.last_failure is not None


def test_closed_records_failure_opens_at_threshold() -> None:
    cb = CircuitBreaker("test", threshold=3, timeout=60)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    assert cb.failure_count == 3


# ---------------------------------------------------------------------------
# State: OPEN
# ---------------------------------------------------------------------------

def test_open_blocks_calls() -> None:
    cb = CircuitBreaker("test", threshold=2, timeout=60)
    for _ in range(2):
        cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN

    provider = _FakeProvider()
    with pytest.raises(OpenStateError):
        cb.call(provider.chat, "hi")


def test_open_is_not_available() -> None:
    cb = CircuitBreaker("test", threshold=1, timeout=60)
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    assert cb.is_available is False


def test_open_provides_clear_error_message() -> None:
    cb = CircuitBreaker("my-ollama", threshold=1, timeout=60)
    cb.record_failure()
    with pytest.raises(OpenStateError) as exc_info:
        cb.call(MagicMock(), "x")
    assert "my-ollama" in str(exc_info.value)
    assert "open" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# State: HALF_OPEN (timeout transition via public call)
# ---------------------------------------------------------------------------

def test_half_open_on_successful_call_after_timeout() -> None:
    """Circuit yang sudah OPEN kembali ke CLOSED setelah timeout & call sukses."""
    cb = CircuitBreaker("test", threshold=1, timeout=0)
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN

    # Force timeout: set last_failure jauh di masa lalu
    cb.last_failure = datetime.now() - timedelta(seconds=1)
    cb._check_timeout()
    assert cb.state == CircuitBreaker.HALF_OPEN

    # Public call sukses → transisi ke CLOSED
    provider = _FakeProvider()
    result = cb.call(provider.chat, "hi")
    assert result == "reply:hi"
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failure_count == 0


def test_half_open_on_failed_call_after_timeout() -> None:
    """Circuit yang sudah OPEN kembali ke OPEN setelah timeout & call gagal."""
    cb = CircuitBreaker("test", threshold=1, timeout=0)
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN

    cb.last_failure = datetime.now() - timedelta(seconds=1)
    cb._check_timeout()
    assert cb.state == CircuitBreaker.HALF_OPEN

    error = RuntimeError("boom")
    provider = _FakeProvider(chat_side_effect=error)
    with pytest.raises(RuntimeError):
        cb.call(provider.chat, "hi")
    assert cb.state == CircuitBreaker.OPEN


def test_half_open_failure_reopens_circuit() -> None:
    cb = CircuitBreaker("test", threshold=1, timeout=60)
    cb.last_failure = datetime.now() - timedelta(seconds=61)
    cb._check_timeout()

    error = RuntimeError("boom")
    provider = _FakeProvider(chat_side_effect=error)
    with pytest.raises(RuntimeError):
        cb.call(provider.chat, "hi")
    assert cb.state == CircuitBreaker.OPEN


def test_half_open_is_available() -> None:
    cb = CircuitBreaker("test", threshold=1, timeout=60)
    cb.last_failure = datetime.now() - timedelta(seconds=61)
    cb._check_timeout()
    assert cb.is_available is True


# ---------------------------------------------------------------------------
# call() with failing function
# ---------------------------------------------------------------------------

def test_call_propagates_exception_from_provider() -> None:
    cb = CircuitBreaker("test", threshold=3)
    error = ConnectionError("timeout")
    provider = _FakeProvider(chat_side_effect=error)
    with pytest.raises(ConnectionError):
        cb.call(provider.chat, "hi")
    assert cb.failure_count == 1
    assert cb.state == CircuitBreaker.CLOSED


def test_call_records_failure_then_opens() -> None:
    cb = CircuitBreaker("test", threshold=2, timeout=60)
    error = ConnectionError("timeout")

    provider = _FakeProvider(chat_side_effect=error)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(provider.chat, "hi")

    assert cb.state == CircuitBreaker.OPEN


# ---------------------------------------------------------------------------
# Metrics snapshot
# ---------------------------------------------------------------------------

def test_snapshot_returns_metric_dict() -> None:
    cb = CircuitBreaker("my-ollama", threshold=3, timeout=60)
    cb.record_failure()
    snap = cb.snapshot()
    assert snap["circuit_name"] == "my-ollama"
    assert snap["circuit_state"] == CircuitBreaker.CLOSED
    assert snap["failure_count"] == 1
    assert snap["last_failure"] is not None


# ---------------------------------------------------------------------------
# wrap_provider
# ---------------------------------------------------------------------------

def test_wrap_provider_returns_chat_wrapper() -> None:
    cb = CircuitBreaker("test", threshold=3, timeout=60)
    provider = _FakeProvider()
    wrapped = cb.wrap_provider(provider)

    result = wrapped.chat("hello")
    assert result == "reply:hello"
    assert provider.chat_calls == ["hello"]  # delegated to inner


def test_wrap_provider_respects_circuit_open() -> None:
    cb = CircuitBreaker("test", threshold=1, timeout=60)
    cb.record_failure()
    provider = _FakeProvider()
    wrapped = cb.wrap_provider(provider)

    with pytest.raises(OpenStateError):
        wrapped.chat("hello")
    assert len(provider.chat_calls) == 0  # never called


def test_wrap_provider_stream_works() -> None:
    cb = CircuitBreaker("test", threshold=3, timeout=60)
    provider = _FakeProvider()
    wrapped = cb.wrap_provider(provider)

    chunks = list(wrapped.chat_stream("hi"))
    assert chunks == ["hello", "world"]


# ---------------------------------------------------------------------------
# is_available property
# ---------------------------------------------------------------------------

def test_closed_is_available() -> None:
    assert CircuitBreaker("t", threshold=3).is_available is True


def test_open_not_available() -> None:
    cb = CircuitBreaker("t", threshold=1, timeout=60)
    cb.record_failure()
    assert cb.is_available is False


def test_half_open_is_available() -> None:
    cb = CircuitBreaker("t", threshold=1, timeout=60)
    cb.last_failure = datetime.now() - timedelta(seconds=61)
    cb._check_timeout()
    assert cb.is_available is True
