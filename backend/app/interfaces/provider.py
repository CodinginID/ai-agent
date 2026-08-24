# app/interfaces/provider.py
"""HTTP endpoint untuk kustomisasi AI Provider per-user."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.adapters.ai_provider_factory import build_ai_provider
from app.adapters.user_provider_config import UserProviderConfigRepository
from app.composition import _session_factory
from app.config import settings
from app.interfaces.auth import _resolve_session_user

router = APIRouter(prefix="/provider", tags=["provider"])


class ProviderUpdateRequest(BaseModel):
    provider: str
    model: str | None = None


@router.get("")
async def get_my_provider(
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    resolved = _resolve_session_user(authorization)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired session",
        )
    user_id, _ = resolved

    repo = UserProviderConfigRepository(_session_factory())
    pref = repo.get(user_id)
    if pref is None:
        return JSONResponse({
            "provider": settings.ai_provider_default,
            "model": settings.qwen_model if settings.ai_provider_default == "ollama" else settings.anthropic_model,
            "is_default": True,
        })

    provider, model = pref
    return JSONResponse({
        "provider": provider,
        "model": model or (settings.qwen_model if provider == "ollama" else settings.anthropic_model),
        "is_default": False,
    })


@router.post("")
async def update_my_provider(
    payload: ProviderUpdateRequest,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    resolved = _resolve_session_user(authorization)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired session",
        )
    user_id, _ = resolved

    # Validasi provider name lewat build_ai_provider
    try:
        build_ai_provider(payload.provider, payload.model, settings)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    repo = UserProviderConfigRepository(_session_factory())
    repo.set(user_id, payload.provider.strip().lower(), payload.model)
    return JSONResponse({"ok": True})
