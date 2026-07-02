"""Health endpoint — aggregated, best-effort dependency status.

Replaces the old inline ``/health`` in ``gateway.py``. Reports:

* ``version``   — git short SHA baked at build time (``APP_VERSION`` env) with a
  runtime ``git rev-parse`` fallback for local dev.
* ``dependencies`` — redis / ollama / database reachability. Each probe is
  best-effort: a failure yields ``"down"`` (never a 500), and any dependency
  down flips the top-level ``status`` to ``"degraded"``.

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


@router.get("/health")
async def health() -> dict[str, object]:
    """Aggregated health — version + best-effort dependency probes."""
    redis_status, ollama_status, db_status = await asyncio.gather(
        _safe(_check_redis, "redis"),
        _safe(_check_ollama, "ollama"),
        _safe(_check_database, "database"),
    )
    deps = {"redis": redis_status, "ollama": ollama_status, "database": db_status}
    overall = "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    return {
        "status": overall,
        "version": _version(),
        "dependencies": deps,
    }
