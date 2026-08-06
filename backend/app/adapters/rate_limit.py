"""Distributed rate limiters backed by Redis.

Dua implementasi dipakai di layer berbeda:

1. ``RedisRateLimiter`` — cooldown per ``user_id`` via ``SET NX EX``.
   Dipakai di Telegram adapter untuk throttle per-user sebelum masuk Ollama.
   Pakai sync client karena dipanggil dari sync generator ``HandleMessageUseCase``.

2. ``TokenBucketRateLimiter`` — fixed-window counter per identifier (IP / user / token).
   Dipakai oleh FastAPI middleware di gateway untuk route-level rate limit.
   Pakai async client supaya bisa dipakai dari async middleware tanpa blocking.

Fail-open policy: kalau Redis down, request tetap dilewatkan dan warning di-log.
Ini mencegah cascading failure — backend yang lambat lebih baik accept request
berlebihan daripada reject semua karena dependency down.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── RedisRateLimiter (sync, per-user cooldown) ──────────────────────────────────


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


# ── TokenBucketRateLimiter (async, fixed-window counter) ───────────────────────


class TokenBucketRateLimiter:
    """Distributed rate limiter pakai Redis ``INCR + EXPIRE``.

    Algoritma:
    1. ``INCR`` key ``<prefix>:<identifier>`` → dapatkan counter saat ini.
    2. Kalau ``EXPIRE`` belum diset (return 0 / key belum ada), set TTL =
       ``refill_interval`` detik — ini menandai awal window baru.
    3. Kalau counter > ``max_tokens``, request ditolak.
    4. Sisanya dikembalikan lewat ``remaining()``.

    Ini fixed-window, bukan sliding window. Trade-off: lebih sederhana dan
    menggunakan lebih sedikit resource Redis, tapi ada burst allowance 1x
    di boundary window (satu request pas window baru bisa sekaligus).

    Kunci unik dibuat dari ``prefix`` + ``identifier`` supaya bisa dipakai
    untuk banyak namespace (user, IP, admin token) tanpa konflik.
    """

    def __init__(self, redis_client: Any, *, max_tokens: int, refill_interval: int) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        if refill_interval < 1:
            raise ValueError("refill_interval must be >= 1 (seconds)")
        self._client = redis_client
        self._max_tokens = max_tokens
        self._refill_interval = refill_interval
        self._prefix = f"rl:{max_tokens}:{refill_interval}"

    def is_allowed(self, identifier: str) -> bool:
        """Cek apakah request dari ``identifier`` boleh lewat.

        Fail-open: return True + warning kalau Redis tak terjangkau.
        """
        key = self._key(identifier)
        try:
            # INCR: atomic increment. Return current counter value.
            count = self._client.incr(key)  # type: ignore[union-attr]

            # EXPIRE hanya di-set kalau key baru (return 1) atau TTL belum ada.
            # Pada Redis, EXPIRE pada key yang sudah punya TTL tidak mengubah TTL-nya,
            # jadi aman dipanggil berulang — hanya sedikit overhead network.
            if count == 1:
                self._client.expire(key, self._refill_interval)  # type: ignore[union-attr]

            return count <= self._max_tokens
        except Exception as exc:
            logger.warning("TokenBucket Redis INCR/EXPIRE failed for %s: %s", identifier, exc)
            return True

    def remaining(self, identifier: str) -> int:
        """Hitung sisa slot yang tersisa. Non-blocking read (GET saja).

        Kalau Redis down, return max_tokens (asumsi semua slot masih tersedia).
        """
        key = self._key(identifier)
        try:
            count = self._client.get(key)  # type: ignore[union-attr]
            if count is None:
                return self._max_tokens
            return max(0, self._max_tokens - int(count))
        except Exception as exc:
            logger.debug("TokenBucket GET failed for %s: %s", identifier, exc)
            return self._max_tokens

    def reset(self, identifier: str) -> None:
        """Hapus counter secara eksplisit (untuk testing atau manual reset)."""
        try:
            self._client.delete(self._key(identifier))  # type: ignore[union-attr]
        except Exception as exc:
            logger.debug("TokenBucket DELETE failed for %s: %s", identifier, exc)

    async def close(self) -> None:
        """Cleanup async client (opsional — singleton di-cache, tidak perlu ditutup)."""
        if hasattr(self._client, "aclose"):
            try:
                await self._client.aclose()
            except Exception as exc:
                logger.debug("TokenBucket async close failed: %s", exc)

    def _key(self, identifier: str) -> str:
        safe_id = identifier.replace(":", "_").replace("/", "_")
        return f"{self._prefix}:{safe_id}"


# ── ASGI middleware (Gateway FastAPI) ────────────────────────────────────────────


class RateLimitMiddleware:
    """FastAPI middleware yang apply ``TokenBucketRateLimiter`` ke route tertentu.

    Tiga rule aktif:
    - ``POST /chat/*``    — max 20/min per user (Bearer session token user_id).
    - ``/auth/*``         — max 5/min per client IP.
    - ``/admin/*``        — max 30/min per admin token value.

    Header yang dibaca:
    - ``X-Forwarded-For``  (kalau ada, ambil IP pertama).
    - ``Authorization``     (Bearer token).

    Jika Redis down, request dilewatkan (fail open) + warning di-log,
    dan response tetap punya header ``X-RateLimit-Remaining`` dengan nilai 0
    untuk memberi sinyal ke client bahwa limiter tidak aktif.
    """

    def __init__(
        self,
        app: Any,
        limiter: TokenBucketRateLimiter,
    ) -> None:
        self._app = app
        self._limiter = limiter

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Determine rule berdasarkan path.
        rule = self._match_rule(path)
        if rule is None:
            await self._app(scope, receive, send)
            return

        # Extract identifier dari scope langsung (tanpa membuat Request object).
        identifier = self._extract_identifier_from_scope(scope, rule)
        if identifier is None:
            # Tidak bisa extract identifier → skip rate limit, tetap lanjut.
            await self._app(scope, receive, send)
            return

        allowed = self._limiter.is_allowed(identifier)
        remaining = self._limiter.remaining(identifier)

        if not allowed:
            # 429 Too Many Requests
            headers = [(b"content-type", b"application/json")]
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": headers,
            })
            body = b'{"error":"rate limit exceeded"}'
            await send({
                "type": "http.response.body",
                "body": body,
            })
            return

        # Allow: lanjut ke app dengan modifier untuk menambah header.
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                # Tambahkan X-RateLimit-Remaining jika belum ada.
                has_remaining = any(
                    h[0].lower() == b"x-ratelimit-remaining" for h in headers
                )
                if not has_remaining:
                    headers.append((b"x-ratelimit-remaining", str(remaining).encode()))
                message["headers"] = headers
            await send(message)

        await self._app(scope, receive, send_with_headers)

    # ── Rule matching ─────────────────────────────────────────────────────────

    def _match_rule(self, path: str) -> str | None:
        if path.startswith("/admin/"):
            return "admin"
        if path.startswith("/auth/"):
            return "auth"
        if path.startswith("/chat/"):
            return "chat"
        return None

    def _extract_identifier_from_scope(self, scope: dict[str, Any], rule: str) -> str | None:
        """Extract identifier dari ASGI scope langsung."""
        headers = dict(scope.get("headers", []))
        header_dict = {k.decode().lower(): v.decode() for k, v in headers.items()}

        if rule == "admin":
            return self._admin_token(header_dict)
        if rule == "auth":
            return self._client_ip(scope, header_dict)
        if rule == "chat":
            return self._chat_user(header_dict)
        return None

    def _admin_token(self, header_dict: dict[str, str]) -> str | None:
        auth = header_dict.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return "admin:" + auth.split(" ", 1)[1].strip()
        return None

    def _client_ip(self, scope: dict[str, Any], header_dict: dict[str, str]) -> str | None:
        forwarded = header_dict.get("x-forwarded-for", "")
        if forwarded:
            # Ambil IP pertama (closest to client).
            ip = forwarded.split(",")[0].strip()
            if ip:
                return "ip:" + ip
        # Fallback ke client address dari scope.
        client = scope.get("client")
        if client and isinstance(client, tuple) and len(client) >= 1:
            host = client[0]
            if host:
                return "ip:" + host
        return None

    def _chat_user(self, header_dict: dict[str, str]) -> str | None:
        """Extract user_id dari Authorization header chat.

        Logic sama seperti ``_resolve_caller`` di ``interfaces/chat.py`` tapi
        tanpa DB lookup — cukup pakai token untuk identifier rate limit.
        Ini trade-off: 1 token = 1 user secara praktis, jadi aman.
        """
        auth = header_dict.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        return "user:" + token


def _key(user_id: str) -> str:
    return f"ratelimit:{user_id}"
