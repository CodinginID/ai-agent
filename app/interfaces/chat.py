"""HTTP endpoint untuk chat — TUI/klien lain kirim pesan ke bot via SSE.

Flow:
1. Klien POST ``/chat/send`` dengan ``{"text": "...", "as_email": "x@y.com"}``.
2. Auth: Bearer ``ADMIN_TOKEN`` (admin bisa chat sebagai user mana pun).
3. Backend resolve email → user_id, build ``HandleMessageUseCase``, jalankan.
4. Setiap ``ChatEvent`` di-emit sebagai Server-Sent Event.

SSE format:
```
event: <type>
data: <json>

```
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Body, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.adapters.database.models import UserModel
from app.adapters.database.session import session_scope
from app.adapters.sessions import UserSessionRepository
from app.composition import _session_factory, build_use_case
from app.config import BASE_DIR, settings
from app.domain.messaging import ChatEvent, MessageContext

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _resolve_caller(authorization: str | None) -> tuple[str, str]:
    """Return (user_id, identity_label) untuk request chat.

    Dua mode auth:
    - Bearer ``ADMIN_TOKEN`` + ``as_email`` di body → admin override (lihat chat_send).
    - Bearer session token (dari TUI login flow) → user identity.

    Method ini hanya handle session-token path; admin path di-handle inline.
    """
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()

    # Admin token? Handler harus pass as_email lewat body — di sini kita raise
    # supaya caller tahu untuk fallback ke admin path.
    if settings.admin_token and token == settings.admin_token:
        return ("__ADMIN__", "admin")

    repo = UserSessionRepository(_session_factory())
    info = repo.resolve(token)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return (info.user_id, "user")


class ChatSendRequest(BaseModel):
    text: str
    # Hanya dipakai kalau caller adalah admin token (admin chat sebagai user X).
    # Kalau session token, field ini diabaikan.
    as_email: str | None = None


def _resolve_admin_target(email: str) -> str:
    with session_scope(_session_factory()) as session:
        user = session.scalar(select(UserModel).where(UserModel.email == email))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"user with email '{email}' not found",
            )
        return user.id


def _format_sse(event: ChatEvent) -> str:
    return f"event: {event.type.value}\ndata: {json.dumps(event.payload, ensure_ascii=False)}\n\n"


async def _stream_events(text: str, ctx: MessageContext) -> AsyncIterator[str]:
    """Jalankan use case di thread (sync generator) lalu pump ke async stream."""
    use_case = build_use_case()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()

    def producer() -> None:
        try:
            for ev in use_case.handle(text, ctx):
                loop.call_soon_threadsafe(queue.put_nowait, ev)
        except Exception as exc:  # pragma: no cover — defensive
            logger.exception("use case crashed")
            loop.call_soon_threadsafe(
                queue.put_nowait,
                ChatEvent.error(f"internal error: {exc}"),
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    task = asyncio.create_task(asyncio.to_thread(producer))
    try:
        while True:
            ev = await queue.get()
            if ev is None:
                break
            yield _format_sse(ev)
        yield "event: done\ndata: {}\n\n"
    finally:
        await task


@router.post("/send")
async def chat_send(
    req: ChatSendRequest = Body(...),
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")

    caller_user_id, mode = _resolve_caller(authorization)

    if mode == "admin":
        if not req.as_email:
            raise HTTPException(
                status_code=400,
                detail="admin token requires 'as_email' field",
            )
        user_id = _resolve_admin_target(req.as_email)
        conv_id = req.as_email
    else:
        user_id = caller_user_id
        conv_id = caller_user_id

    ctx = MessageContext(
        user_id=user_id,
        conversation_id=conv_id,
        project_id=str(BASE_DIR),
        project_root=BASE_DIR,
        project_name="default",
    )

    return StreamingResponse(
        _stream_events(text, ctx),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
