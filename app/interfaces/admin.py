"""Admin HTTP API — diakses oleh TUI dan klien lain.

Auth: Bearer token via ``ADMIN_TOKEN`` di env. Kalau ``ADMIN_TOKEN`` kosong,
semua endpoint di sini akan return ``503`` — supaya tidak ter-expose tanpa
sengaja di production.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.database.models import UserModel
from app.adapters.database.session import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from app.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


# ── auth dependency ──────────────────────────────────────────────────────────

def _require_admin_token(authorization: str | None = Header(default=None)) -> None:
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_TOKEN not configured",
        )
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    provided = authorization.split(" ", 1)[1].strip()
    if provided != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── shared session helper ────────────────────────────────────────────────────

def _open_session() -> Session:
    """Pendek dan eager — admin endpoint umumnya pakai 1 transaction.

    Engine di-cache module-level supaya tidak SSL-handshake ke Neon tiap request.
    """
    return _factory()()


_cached_factory: Any = None


def _factory() -> Any:
    global _cached_factory
    if _cached_factory is None:
        _cached_factory = create_session_factory(
            create_database_engine(settings.database_url)
        )
    return _cached_factory


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/status", dependencies=[Depends(_require_admin_token)])
def get_status() -> dict[str, Any]:
    mode = "polling" if not settings.webhook_url else "webhook"
    with session_scope(_factory()) as session:
        user_count = session.scalar(select(func.count()).select_from(UserModel)) or 0
    return {
        "mode": mode,
        "user_count": user_count,
        "version": "0.1.0",
    }


@router.get("/users", dependencies=[Depends(_require_admin_token)])
def list_users() -> dict[str, Any]:
    with session_scope(_factory()) as session:
        users = list(session.scalars(select(UserModel).order_by(UserModel.created_at)))
        payload = [
            {
                "id": u.id,
                "email": u.email,
                "display_name": u.display_name,
                "telegram_accounts": [
                    {
                        "telegram_user_id": a.telegram_user_id,
                        "username": a.username,
                        "first_name": a.first_name,
                    }
                    for a in u.telegram_accounts
                ],
                "created_at": _iso(u.created_at),
            }
            for u in users
        ]
    return {"users": payload}


@router.post("/logout/{email}", dependencies=[Depends(_require_admin_token)])
def logout_user(email: str) -> dict[str, Any]:
    with session_scope(_factory()) as session:
        user = session.scalar(select(UserModel).where(UserModel.email == email))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"user with email '{email}' not found",
            )
        n_tg = len(user.telegram_accounts)
        n_dev = len(user.devices)
        for tg in list(user.telegram_accounts):
            session.delete(tg)
        for dev in list(user.devices):
            session.delete(dev)
    return {
        "email": email,
        "removed_telegram": n_tg,
        "removed_devices": n_dev,
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


# ── Worker dispatch test (Fase B2 verification) ──────────────────────────────

@router.post("/dispatch-test", dependencies=[Depends(_require_admin_token)])
async def dispatch_test(payload: dict[str, Any]) -> Any:
    """Test endpoint: kirim job ke worker user, stream event balik via SSE.

    Body: ``{"user_id": "<uuid>", "agent": "echo", "prompt": "halo"}``.
    Worker side (TUI) harus implement handler untuk agent ``echo`` — minimal
    mock yang reply 1-2 chunk + done.
    """
    import json as _json

    from fastapi.responses import StreamingResponse

    from app.interfaces.worker_ws import (
        NoWorkerAvailableError,
        dispatch_agent_job,
    )

    user_id = str(payload.get("user_id", "")).strip()
    agent = str(payload.get("agent", "echo")).strip()
    prompt = str(payload.get("prompt", "")).strip()
    if not user_id or not prompt:
        raise HTTPException(400, "user_id & prompt required")

    async def _stream() -> Any:
        try:
            async for event in dispatch_agent_job(user_id, agent, prompt):
                yield f"data: {_json.dumps(event)}\n\n"
        except NoWorkerAvailableError as exc:
            yield f"data: {_json.dumps({'type':'no_worker','message':str(exc)})}\n\n"
        yield "data: {\"type\":\"end\"}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


# ── Audit log via Redis Streams ──────────────────────────────────────────────

@router.get("/audit", dependencies=[Depends(_require_admin_token)])
async def get_audit(n: int = 50, user_id: str = "") -> dict[str, Any]:
    """Recent audit events (chat & agent dispatch). ?user_id= filter optional."""
    from app.adapters.audit import recent
    events = await recent(n=min(max(1, n), 500), user_id=user_id or None)
    return {"events": events, "count": len(events)}


@router.get("/jobs/{job_id}", dependencies=[Depends(_require_admin_token)])
async def get_job(job_id: str) -> dict[str, Any]:
    """Inspect persistent job state (Redis hash). Untuk debug & retry."""
    from app.adapters import job_store
    data = await job_store.get(job_id)
    if data is None:
        raise HTTPException(404, f"job {job_id} not found (mungkin sudah expired)")
    return {"job_id": job_id, **data}
