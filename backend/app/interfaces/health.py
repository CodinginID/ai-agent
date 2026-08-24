"""Health endpoint — aggregated, best-effort dependency status + detail probes.

Replaces the old inline ``/health`` in ``gateway.py``. Reports:

* ``version``   — git short SHA baked at build time (``APP_VERSION`` env) with a
  runtime ``git rev-parse`` fallback for local dev.
* ``dependencies`` — redis / ollama / database reachability. Each probe is
  best-effort: a failure yields ``"down"`` (never a 500), and any dependency
  down flips the top-level ``status`` to ``"degraded"``.
* ``details`` — best-effort metadata. Each entry is ``null`` on failure so the
  dashboard can still render the response without special-casing.

Kept dependency-light and free of side effects so the dashboard can poll it
every few seconds without cost.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx
from fastapi import APIRouter

from app.config import settings
from app.executor.runner import run_safe

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

_PROBE_TIMEOUT_SEC = 3.0


def _version() -> str:
    """Baked build version, falling back to a runtime git lookup for dev."""
    baked = os.getenv("APP_VERSION", "").strip()
    if baked:
        return baked
    git_head, rc = run_safe(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=settings.project_dir,
        timeout=5,
    )
    return git_head.strip() if rc == 0 and git_head.strip() else "unknown"


async def _check_redis() -> bool:
    from app.adapters import redis_client

    return await redis_client.ping()


async def _check_ollama() -> bool:
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SEC) as client:
        resp = await client.get(f"{settings.ollama_host}/api/tags")
        return resp.status_code == 200


async def _check_database() -> bool:
    from sqlalchemy import text

    from app.adapters.database.session import (
        create_database_engine,
        create_session_factory,
        session_scope,
    )

    def _probe() -> bool:
        engine = create_database_engine(settings.database_url)
        try:
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                session.execute(text("SELECT 1"))
            return True
        finally:
            engine.dispose()

    return await asyncio.to_thread(_probe)


async def _safe(probe: object, name: str) -> str:
    try:
        ok = await probe()  # type: ignore[operator]
        return "ok" if ok else "down"
    except Exception as exc:
        logger.warning("health probe %s failed: %s", name, exc)
        return "down"


async def _safe_detail(probe: object, name: str) -> object | None:
    """Best-effort detail probe: return the result or ``None`` on failure.

    Unlike ``_safe`` (which returns ``"ok"``/``"down"`` for reachability probes),
    these probes enrich the response with metadata. A failure is **never**
    surfaced as a status flip; the field is simply ``null``.
    """
    try:
        return await probe()  # type: ignore[operator]
    except Exception as exc:
        logger.debug("health detail %s failed: %s", name, exc)
        return None


async def _check_ollama_models() -> int | None:
    """Count of Ollama models loaded into memory (``/api/tags`` response).

    Returns ``None`` if the Ollama API is unreachable so the detail field stays
    null instead of zeroing out the count.
    """
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SEC) as client:
        resp = await client.get(f"{settings.ollama_host}/api/tags")
        resp.raise_for_status()
        data = resp.json()
    models = data.get("models") or []
    return len(models)


async def _check_db_migration_head() -> str | None:
    """Current Alembic migration head.

    Best-effort: falls back to ``None`` if Alembic isn't installed or the
    migration directory is missing.
    """
    result = run_safe(
        ["alembic", "current"],
        cwd=settings.project_dir,
        timeout=5,
    )
    if result[1] != 0:
        return None
    # Alembic prints the migration id; strip the trailing newline.
    return result[0].strip() or None


async def _check_queue_depth() -> int | None:
    """Total job queue depth across all user queues.

    Scans ``job:queue:*`` keys via Redis SCAN and sums ``LLEN`` per key.
    Returns ``None`` if Redis is down or the SCAN fails.
    """
    from app.adapters import redis_client

    client = redis_client.get_client()
    try:
        total = 0
        async for key in client.scan_iter(match="job:queue:*", count=100):
            length = await client.llen(key)
            if length:
                total += length
        return total
    except Exception:
        return None


async def _check_workers_registered() -> int | None:
    """Count of registered workers.

    Scans ``workers:*`` keys and sums ``SCARD`` per key. Returns ``None`` if
    Redis is down or the SCAN fails.
    """
    from app.adapters import redis_client

    client = redis_client.get_client()
    try:
        total = 0
        async for key in client.scan_iter(match="workers:*", count=100):
            card = await client.scard(key)
            if card:
                total += card
        return total
    except Exception:
        return None


@router.get("/health")
async def health() -> dict[str, object]:
    """Aggregated health — version + best-effort dependency probes + details."""
    redis_status, ollama_status, db_status = await asyncio.gather(
        _safe(_check_redis, "redis"),
        _safe(_check_ollama, "ollama"),
        _safe(_check_database, "database"),
    )
    detail_results = await asyncio.gather(
        _safe_detail(_check_ollama_models, "ollama_models"),
        _safe_detail(_check_db_migration_head, "migration_head"),
        _safe_detail(_check_queue_depth, "queue_depth"),
        _safe_detail(_check_workers_registered, "workers_registered"),
    )
    models_loaded, migration_head, queue_depth, workers_registered = detail_results
    deps = {"redis": redis_status, "ollama": ollama_status, "database": db_status}
    overall = "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    return {
        "status": overall,
        "version": _version(),
        "dependencies": deps,
        "details": {
            "models_loaded": models_loaded,
            "migration_head": migration_head,
            "queue_depth": queue_depth,
            "workers_registered": workers_registered,
        },
    }
