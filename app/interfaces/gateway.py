import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.interfaces.admin import router as admin_router
from app.interfaces.auth import router as auth_router
from app.interfaces.chat import router as chat_router
from app.interfaces.worker_ws import router as worker_ws_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        from app.adapters import job_store
        n = await job_store.mark_abandoned_for_instance(settings.instance_id)
        if n:
            logger.warning("marked %d abandoned jobs from previous run", n)
    except Exception:
        logger.exception("failed to scan abandoned jobs")

    try:
        from app.interfaces.worker_ws import start_pubsub_listener
        await start_pubsub_listener()
    except Exception:
        logger.exception("failed to start pubsub listener")

    yield

    try:
        from app.interfaces.worker_ws import stop_pubsub_listener
        await stop_pubsub_listener()
    except Exception:
        logger.exception("failed to stop pubsub listener")


app = FastAPI(title="Octopus Core", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(worker_ws_router)


@app.get("/health")
async def health() -> dict[str, object]:
    """Public health endpoint — git HEAD, compose services, app status."""
    import asyncio

    from app.config import settings
    from app.executor.runner import run_safe

    def _check() -> dict[str, object]:
        git_head, _ = run_safe(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=settings.project_dir,
            timeout=5,
        )
        _, compose_rc = run_safe(
            ["docker", "compose", "ps"],
            cwd=settings.project_dir,
            timeout=5,
        )
        return {
            "status": "ok",
            "git_head": git_head.strip(),
            "compose": "ok" if compose_rc == 0 else "unavailable",
        }

    return await asyncio.to_thread(_check)
