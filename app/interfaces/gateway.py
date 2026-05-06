import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from telegram import Update
from telegram.ext import Application

from app.bot import build_application
from app.config import settings
from app.interfaces.admin import router as admin_router
from app.interfaces.auth import router as auth_router
from app.interfaces.chat import router as chat_router
from app.interfaces.worker_ws import router as worker_ws_router

logger = logging.getLogger(__name__)

_telegram_app: Application[Any] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _telegram_app

    # Startup hook: tandai semua job yang lagi running tapi backend mati di
    # tengah jalan sebagai "abandoned". Bantu user tahu kalau retry diperlukan.
    try:
        from app.adapters import job_store
        n = await job_store.mark_abandoned_for_instance(settings.instance_id)
        if n:
            logger.warning("marked %d abandoned jobs from previous run", n)
    except Exception:
        logger.exception("failed to scan abandoned jobs")

    # Multi-instance routing (B5g): subscribe ke channel pub/sub kita supaya
    # bisa terima reply yang originally dispatched dari instance ini.
    try:
        from app.interfaces.worker_ws import start_pubsub_listener
        await start_pubsub_listener()
    except Exception:
        logger.exception("failed to start pubsub listener")

    _telegram_app = build_application()
    await _telegram_app.initialize()

    if settings.webhook_url:
        webhook_endpoint = f"{settings.webhook_url}/webhook/telegram"
        await _telegram_app.bot.set_webhook(
            url=webhook_endpoint,
            secret_token=settings.webhook_secret or None,
        )
        logger.info("Webhook registered: %s", webhook_endpoint)
    else:
        # Dev / local: run polling alongside FastAPI so both OAuth and bot work
        await _telegram_app.updater.start_polling(  # type: ignore[union-attr]
            allowed_updates=Update.ALL_TYPES,
        )
        logger.info("Polling started (no WEBHOOK_URL set)")

    await _telegram_app.start()
    yield

    if not settings.webhook_url:
        await _telegram_app.updater.stop()  # type: ignore[union-attr]
    await _telegram_app.stop()
    await _telegram_app.shutdown()

    try:
        from app.interfaces.worker_ws import stop_pubsub_listener
        await stop_pubsub_listener()
    except Exception:
        logger.exception("failed to stop pubsub listener")


app = FastAPI(title="AI Agent Gateway", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(worker_ws_router)


@app.get("/health")
async def health() -> dict[str, str]:
    mode = "webhook" if settings.webhook_url else "polling"
    return {"status": "ok", "mode": mode}


@app.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    if settings.webhook_secret and x_telegram_bot_api_secret_token != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    if _telegram_app is None:
        return Response(status_code=503)

    data = await request.json()
    update = Update.de_json(data, _telegram_app.bot)
    await _telegram_app.process_update(update)
    return Response(status_code=200)
