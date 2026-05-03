import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from telegram import Update
from telegram.ext import Application

from app.bot import build_application
from app.config import settings

logger = logging.getLogger(__name__)

_telegram_app: Application[Any] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _telegram_app
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
        logger.warning("WEBHOOK_URL not set — webhook not registered with Telegram")

    await _telegram_app.start()
    yield

    await _telegram_app.stop()
    await _telegram_app.shutdown()


app = FastAPI(title="AI Agent Gateway", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "webhook"}


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
