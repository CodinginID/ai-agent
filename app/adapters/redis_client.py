"""Redis async client (singleton).

Dipakai untuk:
- Worker presence  (``workers:<user_id>`` set + TTL)
- Job queue        (``job:queue:<user_id>`` list, BRPOP)
- Job stream       (``job:stream:<job_id>`` pub/sub)
- Agent context    (``agent:ctx:<session>`` hash) — Fase B5
- Audit            (Redis Streams) — Fase B5

Privat di network internal backend; worker user **tidak** akses Redis langsung.
"""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


def get_client() -> aioredis.Redis:
    """Return singleton Redis async client. Lazy-init satu kali per proses."""
    global _client
    if _client is None:
        _client = aioredis.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url,
            decode_responses=True,
            encoding="utf-8",
            health_check_interval=30,
        )
        logger.info("Redis client created: %s", _safe_url(settings.redis_url))
    return _client


async def ping() -> bool:
    """Simple connectivity check — return True kalau Redis reachable."""
    try:
        client = get_client()
        return bool(await client.ping())
    except Exception as exc:
        logger.warning("Redis ping failed: %s", exc)
        return False


async def close() -> None:
    """Cleanup saat shutdown — tutup koneksi pool."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _safe_url(url: str) -> str:
    """Mask password kalau ada di URL."""
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    _, host = rest.split("@", 1)
    return f"{scheme}://***@{host}"


# ── Key helpers (single source of truth untuk format key) ────────────────────

def k_workers(user_id: str) -> str:
    return f"workers:{user_id}"


def k_worker_meta(worker_id: str) -> str:
    return f"worker:meta:{worker_id}"


def k_job_queue(user_id: str) -> str:
    return f"job:queue:{user_id}"


def k_job(job_id: str) -> str:
    return f"job:{job_id}"


def k_job_stream(job_id: str) -> str:
    return f"job:stream:{job_id}"


def k_agent_ctx(session_id: str) -> str:
    return f"agent:ctx:{session_id}"


def k_audit_stream() -> str:
    return "audit:stream"


def k_caps(user_id: str, agent_id: str) -> str:
    """Set worker_id yang punya CLI agent_id installed (per user)."""
    return f"caps:{user_id}:{agent_id}"


def k_agent_ctx_role(user_id: str, role: str) -> str:
    """Hash hasil terakhir per (user, role) — untuk hand-off antar role."""
    return f"agent:ctx:{user_id}:{role}"


def k_tg_pair(code: str) -> str:
    """Key untuk Telegram pair code (TTL 15 menit)."""
    return f"tg:pair:{code}"


def k_backend_channel(instance_id: str) -> str:
    """Pub/sub channel untuk routing reply antar backend instance."""
    return f"backend:{instance_id}"


# ── Generic helpers ──────────────────────────────────────────────────────────

async def healthcheck() -> dict[str, Any]:
    """Detail untuk /health endpoint, kalau diperlukan."""
    ok = await ping()
    return {"redis": "ok" if ok else "down", "url": _safe_url(settings.redis_url)}
