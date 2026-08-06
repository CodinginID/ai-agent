import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.adapters.logger import json_logger
from app.adapters.trace import TraceMiddleware, current_trace_id
from app.config import settings
from app.interfaces.metrics import MetricsMiddleware
from app.interfaces.admin import router as admin_router
from app.interfaces.auth import router as auth_router
from app.interfaces.chat import router as chat_router
from app.interfaces.context import router as context_router
from app.interfaces.dashboard import router as dashboard_router
from app.interfaces.health import router as health_router
from app.interfaces.provider import router as provider_router
from app.interfaces.skills import router as skills_router
from app.interfaces.tasks import router as tasks_router
from app.interfaces.worker_ws import router as worker_ws_router
from app.interfaces.workflow import router as workflow_router

logger = json_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Gateway starting up")

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

    logger.info("Gateway started successfully")
    yield
    logger.info("Gateway shutting down")

    try:
        from app.interfaces.worker_ws import stop_pubsub_listener
        await stop_pubsub_listener()
    except Exception:
        logger.exception("failed to stop pubsub listener")
    finally:
        logger.info("Gateway shutdown complete")


app = FastAPI(
    title="Octopus Core API",
    version="0.2.0",
    description="Backend API for the Octopus AI agent platform — task orchestration, skill management, and multi-provider LLM routing.",
    contact={"name": "Octopus Team", "email": "dev@octopus.internal"},
    license_info={"name": "MIT"},
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


@app.get("/metrics", response_class=Response)
async def metrics_endpoint() -> Response:
    """Return Prometheus text exposition format metrics."""
    from app.interfaces.metrics import get_metrics

    body = get_metrics()
    return Response(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
app.add_middleware(TraceMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(context_router)
app.include_router(provider_router)
app.include_router(skills_router)
app.include_router(tasks_router)
app.include_router(workflow_router)
app.include_router(worker_ws_router)
app.include_router(health_router)
app.include_router(dashboard_router)
