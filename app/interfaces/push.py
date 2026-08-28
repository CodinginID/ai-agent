"""HTTP endpoint untuk Web Push — subscribe/unsubscribe browser + kirim tes.

Flow:
1. Klien ambil VAPID public key (``GET /push/vapid-public-key``).
2. Klien ``pushManager.subscribe()`` di browser, lalu POST hasilnya ke
   ``/push/subscribe`` (di-resolve ke user_id via token/``as_email`` seperti
   ``/chat/send``).
3. Backend (task observer / chat mirror) mengirim notifikasi lewat
   ``build_push().notify(...)`` saat approval diminta / task selesai.

Auth memakai model yang sama seperti ``/chat``: Bearer session token atau
``ADMIN_TOKEN`` + ``as_email``.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from app.composition import build_push
from app.config import settings
from app.interfaces.chat import _resolve_caller, _resolve_user_and_conv
from app.ports.push import PushMessage, PushSubscription

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["push"])


def _require_configured() -> None:
    if not settings.vapid_public_key or not settings.vapid_private_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="push belum dikonfigurasi (VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY kosong)",
        )


@router.get("/vapid-public-key")
async def vapid_public_key(
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _resolve_caller(authorization)  # gate: 401 kalau token invalid
    _require_configured()
    return {"key": settings.vapid_public_key}


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys
    as_email: str | None = None


class PushUnsubscribeRequest(BaseModel):
    endpoint: str
    as_email: str | None = None


@router.post("/subscribe")
async def push_subscribe(
    req: Annotated[PushSubscribeRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    user_id, _conv_id = _resolve_user_and_conv(authorization, req.as_email)
    _require_configured()
    if not req.endpoint.startswith("https://"):
        raise HTTPException(status_code=400, detail="endpoint harus URL https")

    sub = PushSubscription(
        endpoint=req.endpoint, p256dh=req.keys.p256dh, auth=req.keys.auth
    )
    await build_push().subscribe(user_id, sub)
    return {"ok": True}


@router.post("/unsubscribe")
async def push_unsubscribe(
    req: Annotated[PushUnsubscribeRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    user_id, _conv_id = _resolve_user_and_conv(authorization, req.as_email)
    await build_push().unsubscribe(user_id, req.endpoint)
    return {"ok": True}


@router.post("/test")
async def push_test(
    authorization: str | None = Header(default=None),
) -> dict[str, int]:
    user_id, _mode = _resolve_caller(authorization)
    _require_configured()
    msg = PushMessage(
        title="Octopus",
        body="Tes notifikasi Octopus",
        tag="test",
        kind="test",
        url="/",
    )
    delivered = await build_push().notify(user_id, msg)
    return {"delivered": delivered}
