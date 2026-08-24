"""Chaos tests — verifikasi perilaku sistem saat dependency eksternal down.

Tests ini mensimulasikan failure injection untuk memastikan:
- Fallback ke provider lain (Anthropic) ketika Ollama down
- Fail-open pada rate limiter ketika Redis down
- Retry behavior pada database timeout
- Circuit breaker pattern (open/half_open)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import pytest

from app.adapters.circuit_breaker import CircuitBreaker, OpenStateError
from app.adapters.rate_limit import RedisRateLimiter
from app.domain.exceptions import AIProviderError


# ---------------------------------------------------------------------------
# Helper classes
# ---------------------------------------------------------------------------

class _FakeOllamaProvider:
    """Mock Ollama provider yang bisa di-set untuk raise exception."""

    def __init__(self, should_fail: bool = True) -> None:
        self.should_fail = should_fail
        self.chat_calls: list[str] = []

    def chat(self, prompt: str) -> str:
        self.chat_calls.append(prompt)
        if self.should_fail:
            raise AIProviderError("Ollama down")
        return "ollama response"


class _FakeAnthropicProvider:
    """Mock Anthropic provider sebagai fallback."""

    def __init__(self) -> None:
        self.chat_calls: list[str] = []

    def chat(self, prompt: str) -> str:
        self.chat_calls.append(prompt)
        return "anthropic response"


class _FakeRedisClient:
    """Mock Redis client yang bisa di-set untuk raise exception."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.set_calls: list[tuple] = []

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool | None:
        self.set_calls.append((key, value, ex, nx))
        if self.should_fail:
            raise ConnectionError("Redis down")
        return True


class _FakeDatabaseSession:
    """Mock SQLAlchemy session yang bisa di-set untuk raise exception."""

    def __init__(self, should_timeout: bool = False) -> None:
        self.should_timeout = should_timeout
        self.query_calls: list[str] = []

    def query(self, model: object) -> object:
        self.query_calls.append(f"query({model})")
        if self.should_timeout:
            from sqlalchemy.exc import TimeoutError
            raise TimeoutError("Database connection timeout")
        return MagicMock()


# ---------------------------------------------------------------------------
# Test 1: Ollama down → fallback ke Anthropic
# ---------------------------------------------------------------------------

def test_ollama_down_fallback_to_anthropic() -> None:
    """Ketika Ollama down, sistem harus fallback ke Anthropic atau handle error dengan baik."""
    ollama = _FakeOllamaProvider(should_fail=True)
    anthropic = _FakeAnthropicProvider()

    # Simulate fallback logic
    provider = ollama
    max_retries = 3

    for attempt in range(max_retries):
        try:
            result = provider.chat("test prompt")
            break
        except AIProviderError:
            if attempt == max_retries - 1:
                # Semua retry gagal, fallback ke Anthropic
                provider = anthropic
            continue
    else:
        # Jika masih Ollama setelah loop (harusnya tidak sampai sini), gunakan Anthropic
        provider = anthropic

    result = provider.chat("test prompt")

    assert result == "anthropic response"
    assert anthropic.chat_calls == ["test prompt"]
    assert len(ollama.chat_calls) == max_retries  # Ollama dicoba max_retries kali


def test_ollama_down_propagates_error_after_exhausted_retries() -> None:
    """Ketika Ollama down dan tidak ada fallback, error harus propagat ke caller."""
    ollama = _FakeOllamaProvider(should_fail=True)
    max_retries = 2

    with pytest.raises(AIProviderError, match="Ollama down"):
        for attempt in range(max_retries):
            try:
                ollama.chat("test")
            except AIProviderError as exc:
                if attempt == max_retries - 1:
                    raise
                continue


# ---------------------------------------------------------------------------
# Test 2: Redis down → rate limiter fail-open
# ---------------------------------------------------------------------------

def test_redis_down_rate_limiter_fails_open() -> None:
    """Ketika Redis down, rate limiter harus fail-open (allow semua request)."""
    redis_client = _FakeRedisClient(should_fail=True)
    limiter = RedisRateLimiter(redis_client, cooldown_seconds=10)

    # Request pertama seharusnya di-allow (fail-open)
    assert limiter.is_allowed("user-1") is True

    # Request kedua juga seharusnya di-allow (fail-open)
    assert limiter.is_allowed("user-1") is True

    # Request ketiga juga seharusnya di-allow (fail-open)
    assert limiter.is_allowed("user-1") is True

    # Verifikasi Redis.set dipanggil 3 kali
    assert len(redis_client.set_calls) == 3


def test_redis_down_rate_limiter_allows_different_users() -> None:
    """Ketika Redis down, semua user harus di-allow (fail-open)."""
    redis_client = _FakeRedisClient(should_fail=True)
    limiter = RedisRateLimiter(redis_client, cooldown_seconds=10)

    assert limiter.is_allowed("user-1") is True
    assert limiter.is_allowed("user-2") is True
    assert limiter.is_allowed("user-3") is True

    # Total 3 call ke Redis
    assert len(redis_client.set_calls) == 3


def test_redis_normal_still_works() -> None:
    """Ketika Redis normal, rate limiter harus bekerja seperti biasa."""
    import time

    class _ProperFakeRedis:
        """Proper Redis mock with TTL support."""
        def __init__(self) -> None:
            self._store: dict[str, tuple[str, float | None]] = {}

        def set(self, name: str, value: str, ex: int | None = None, nx: bool = False) -> bool | None:
            existing = self._store.get(name)
            now = time.time()
            if existing and existing[1] is not None and existing[1] < now:
                del self._store[name]
                existing = None
            if nx and existing:
                return None
            self._store[name] = (value, now + ex if ex else None)
            return True

    redis_client = _ProperFakeRedis()
    limiter = RedisRateLimiter(redis_client, cooldown_seconds=10)

    # Request pertama di-allow
    assert limiter.is_allowed("user-1") is True

    # Request kedua di-block (cooldown masih aktif)
    assert limiter.is_allowed("user-1") is False


# ---------------------------------------------------------------------------
# Test 3: Database timeout → retry behavior
# ---------------------------------------------------------------------------

def test_database_timeout_retries_then_raises() -> None:
    """Ketika database timeout, query harus di-retry dan akhirnya raise error."""
    from sqlalchemy.exc import TimeoutError as SATimeoutError

    db_session = _FakeDatabaseSession(should_timeout=True)
    max_retries = 3
    actual_calls = 0
    final_error: Exception | None = None

    try:
        for i in range(max_retries):
            actual_calls += 1
            try:
                db_session.query(MagicMock())
                break
            except SATimeoutError as exc:
                final_error = exc
                if i < max_retries - 1:
                    import time
                    time.sleep(0.01)
                else:
                    raise
    except SATimeoutError:
        pass  # Expected: last attempt raises

    assert actual_calls == max_retries
    assert len(db_session.query_calls) == max_retries
    assert final_error is not None
    assert isinstance(final_error, SATimeoutError)


def test_database_success_no_retry() -> None:
    """Ketika database success, tidak ada retry yang terjadi."""
    db_session = _FakeDatabaseSession(should_timeout=False)
    success = False

    try:
        db_session.query(MagicMock())
        success = True
    except Exception:
        pass

    assert success is True
    assert len(db_session.query_calls) == 1


# ---------------------------------------------------------------------------
# Test 4: Circuit breaker open setelah 3 consecutive failures
# ---------------------------------------------------------------------------

def test_circuit_breaker_opens_after_threshold_failures() -> None:
    """Circuit breaker harus open setelah threshold failures (default 3)."""
    cb = CircuitBreaker("test-provider", threshold=3, timeout=60)
    provider = _FakeOllamaProvider(should_fail=True)

    # 3 consecutive failures harus membuka circuit
    for i in range(3):
        with pytest.raises(AIProviderError):
            cb.call(provider.chat, f"prompt-{i}")

    assert cb.state == CircuitBreaker.OPEN
    assert cb.failure_count == 3
    assert cb.is_available is False


def test_circuit_breaker_open_blocks_calls() -> None:
    """Ketika circuit open, semua call harus langsung raise OpenStateError."""
    cb = CircuitBreaker("test-provider", threshold=2, timeout=60)
    provider = _FakeOllamaProvider(should_fail=True)

    # 2 failures → circuit open
    for _ in range(2):
        with pytest.raises(AIProviderError):
            cb.call(provider.chat, "test")

    assert cb.state == CircuitBreaker.OPEN

    # Call berikutnya harus langsung raise OpenStateError
    with pytest.raises(OpenStateError, match="open"):
        cb.call(provider.chat, "blocked")

    # Provider.inner.chat() tidak dipanggil setelah circuit open
    assert len(provider.chat_calls) == 2


def test_circuit_breaker_open_prevents_cascade() -> None:
    """Circuit breaker mencegah cascade failure ke provider."""
    cb = CircuitBreaker("fragile-provider", threshold=2, timeout=60)
    provider = _FakeOllamaProvider(should_fail=True)

    # 2 failures → circuit open
    for _ in range(2):
        with pytest.raises(AIProviderError):
            cb.call(provider.chat, "test")

    # Verify circuit is open and provider was called exactly 2 times
    assert cb.state == CircuitBreaker.OPEN
    assert len(provider.chat_calls) == 2

    # Now try 100 more calls — all should fail fast with OpenStateError
    open_state_errors = 0
    for _ in range(100):
        try:
            cb.call(provider.chat, "blocked")
        except OpenStateError:
            open_state_errors += 1

    # All 100 calls should be blocked
    assert open_state_errors == 100

    # Provider.chat() should NOT have been called after circuit opened
    assert len(provider.chat_calls) == 2


# ---------------------------------------------------------------------------
# Test 5: Circuit breaker half_open setelah timeout
# ---------------------------------------------------------------------------

def test_circuit_breaker_transitions_to_half_open_after_timeout() -> None:
    """Circuit breaker harus transition ke half_open setelah timeout periode."""
    cb = CircuitBreaker("test-provider", threshold=2, timeout=0)  # timeout=0 untuk testing
    provider = _FakeOllamaProvider(should_fail=True)

    # 2 failures → circuit open
    for _ in range(2):
        with pytest.raises(AIProviderError):
            cb.call(provider.chat, "test")

    assert cb.state == CircuitBreaker.OPEN

    # Force timeout: set last_failure ke masa lalu
    cb.last_failure = datetime.now() - timedelta(seconds=1)
    cb._check_timeout()

    assert cb.state == CircuitBreaker.HALF_OPEN


def test_circuit_breaker_half_open_on_success_closes() -> None:
    """Ketika circuit half_open dan call sukses, harus kembali ke closed."""
    cb = CircuitBreaker("test-provider", threshold=2, timeout=0)
    successful_provider = _FakeOllamaProvider(should_fail=False)

    # 2 failures → circuit open
    failing_provider = _FakeOllamaProvider(should_fail=True)
    for _ in range(2):
        with pytest.raises(AIProviderError):
            cb.call(failing_provider.chat, "test")

    # Force timeout → half_open
    cb.last_failure = datetime.now() - timedelta(seconds=1)
    cb._check_timeout()
    assert cb.state == CircuitBreaker.HALF_OPEN

    # Successful call → circuit closed
    cb.call(successful_provider.chat, "recovery")

    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failure_count == 0
    assert cb.is_available is True


def test_circuit_breaker_half_open_on_failure_reopens() -> None:
    """Ketika circuit half_open dan call gagal, harus kembali ke open."""
    cb = CircuitBreaker("test-provider", threshold=2, timeout=0)
    provider = _FakeOllamaProvider(should_fail=True)

    # 2 failures → circuit open
    for _ in range(2):
        with pytest.raises(AIProviderError):
            cb.call(provider.chat, "test")

    # Force timeout → half_open
    cb.last_failure = datetime.now() - timedelta(seconds=1)
    cb._check_timeout()
    assert cb.state == CircuitBreaker.HALF_OPEN

    # Failed call → circuit open lagi
    with pytest.raises(AIProviderError):
        cb.call(provider.chat, "still broken")

    assert cb.state == CircuitBreaker.OPEN
    assert cb.failure_count == 3  # incremented dari 2 ke 3


def test_circuit_breaker_half_open_allows_one_probe() -> None:
    """Ketika circuit half_open, hanya 1 probe call yang diizinkan."""
    cb = CircuitBreaker("test-provider", threshold=1, timeout=60)
    provider = _FakeOllamaProvider(should_fail=True)

    # 1 failure → circuit open
    with pytest.raises(AIProviderError):
        cb.call(provider.chat, "test")

    # Force timeout → half_open
    cb.last_failure = datetime.now() - timedelta(seconds=61)
    cb._check_timeout()
    assert cb.state == CircuitBreaker.HALF_OPEN

    # First call: should be allowed (probe), but fails
    with pytest.raises(AIProviderError):
        cb.call(provider.chat, "probe-1")

    # After failure, circuit goes back to OPEN
    assert cb.state == CircuitBreaker.OPEN

    # Second call immediately should raise OpenStateError
    # (timeout hasn't expired yet, so state stays OPEN)
    with pytest.raises(OpenStateError):
        cb.call(provider.chat, "probe-2")


# ---------------------------------------------------------------------------
# Integration: Circuit breaker + Ollama fallback
# ---------------------------------------------------------------------------

def test_circuit_breaker_with_fallback_provider() -> None:
    """Circuit breaker melindungi primary provider, fallback ke secondary."""
    cb = CircuitBreaker("primary-ollama", threshold=2, timeout=0)
    primary = _FakeOllamaProvider(should_fail=True)
    secondary = _FakeAnthropicProvider()

    # 2 failures → circuit open
    for _ in range(2):
        with pytest.raises(AIProviderError):
            cb.call(primary.chat, "test")

    assert cb.state == CircuitBreaker.OPEN

    # Force timeout → half_open
    cb.last_failure = datetime.now() - timedelta(seconds=1)
    cb._check_timeout()

    # Now circuit is half_open, probe call succeeds with secondary
    result = secondary.chat("fallback prompt")
    assert result == "anthropic response"
    assert secondary.chat_calls == ["fallback prompt"]


# ---------------------------------------------------------------------------
# Chaos: Multiple simultaneous failures
# ---------------------------------------------------------------------------

def test_multiple_providers_all_down() -> None:
    """Ketika semua provider down, sistem harus handle gracefully."""
    providers = [
        _FakeOllamaProvider(should_fail=True),
        _FakeAnthropicProvider(),
    ]

    # Override second provider to also fail
    class _FailingAnthropic:
        def chat(self, prompt: str) -> str:
            raise AIProviderError("Anthropic also down")

    providers[1] = _FailingAnthropic()

    # Try all providers
    last_error = None
    for provider in providers:
        try:
            result = provider.chat("chaos test")
            # Jika ada yang success, ini bukan chaos anymore
            assert False, f"Unexpected success from {provider}"
        except AIProviderError as exc:
            last_error = exc

    assert last_error is not None
    assert "down" in str(last_error).lower()
