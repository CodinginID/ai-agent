"""HTTP endpoints untuk Skill CRUD + run streaming.

Auth: Bearer session token (dari TUI login flow). Semua endpoint user-scoped
via project ownership — user tidak bisa list/baca/edit skill milik user lain.

Endpoints:
- ``GET    /skills?project_id=...``       — list skills dalam project
- ``POST   /skills``                       — create skill (body: project_id + definition)
- ``GET    /skills/{skill_id}``            — get satu skill
- ``PUT    /skills/{skill_id}``            — update (re-validate definition)
- ``DELETE /skills/{skill_id}``            — delete
- ``POST   /skills/{skill_id}/run``        — execute via ``SkillExecutor``,
  stream event SSE (skill_started, step_*, skill_completed/failed).

Mapping error:
- ``SkillValidationError`` → 400 Bad Request
- ``DatabaseConflictError`` → 409 Conflict
- Skill not found / not owned → 404 Not Found
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.adapters.agent_configs import UserAgentConfigRepository
from app.adapters.database.repositories import (
    ControlPlaneRepository,
    DatabaseConflictError,
)
from app.adapters.sessions import UserSessionRepository
from app.composition import _session_factory
from app.domain.skills import SkillValidationError, parse_skill, skill_to_dict
from app.orchestrator.skill_executor import SkillEvent, SkillExecutor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/skills", tags=["skills"])


# ── Auth helper ──────────────────────────────────────────────────────────────


def _resolve_user_id(authorization: str | None) -> str:
    """Resolve user_id dari Bearer session token. Raise 401 kalau invalid."""
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    repo = UserSessionRepository(_session_factory())
    info = repo.resolve(token)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return info.user_id


# ── Request/response shapes ──────────────────────────────────────────────────


class SkillCreateRequest(BaseModel):
    project_id: str
    definition: dict[str, Any]


class SkillUpdateRequest(BaseModel):
    definition: dict[str, Any]


class SkillRunRequest(BaseModel):
    prompt: str


def _skill_to_response(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "definition": row.definition,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ── CRUD endpoints ───────────────────────────────────────────────────────────


@router.get("")
async def list_skills(
    project_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """List skills milik project. Empty list kalau project bukan milik user."""
    user_id = _resolve_user_id(authorization)
    with _session_factory()() as session:
        repo = ControlPlaneRepository(session)
        rows = repo.list_project_skills(project_id, user_id)
        return {"skills": [_skill_to_response(r) for r in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_skill(
    req: Annotated[SkillCreateRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    with _session_factory()() as session:
        repo = ControlPlaneRepository(session)
        try:
            row = repo.create_skill(req.project_id, user_id, req.definition)
        except SkillValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        except DatabaseConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        session.commit()
        return _skill_to_response(row)


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    with _session_factory()() as session:
        repo = ControlPlaneRepository(session)
        row = repo.get_skill(skill_id, user_id)
        if row is None:
            raise HTTPException(404, f"Skill {skill_id} tidak ditemukan")
        return _skill_to_response(row)


@router.put("/{skill_id}")
async def update_skill(
    skill_id: str,
    req: Annotated[SkillUpdateRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    with _session_factory()() as session:
        repo = ControlPlaneRepository(session)
        try:
            row = repo.update_skill(skill_id, user_id, req.definition)
        except SkillValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        except DatabaseConflictError as exc:
            # Bisa "skill not found" atau "rename collision" — bedakan via msg.
            msg = str(exc)
            code = 404 if "tidak ditemukan" in msg else 409
            raise HTTPException(code, msg) from exc
        session.commit()
        return _skill_to_response(row)


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    user_id = _resolve_user_id(authorization)
    with _session_factory()() as session:
        repo = ControlPlaneRepository(session)
        if not repo.delete_skill(skill_id, user_id):
            raise HTTPException(404, f"Skill {skill_id} tidak ditemukan")
        session.commit()
    return {"deleted": True}


# ── Validate endpoint (dry-run schema check) ─────────────────────────────────


@router.post("/validate")
async def validate_skill(
    req: Annotated[SkillUpdateRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Dry-run parse — useful untuk UI 'cek dulu sebelum save'."""
    _resolve_user_id(authorization)  # auth required, no DB write
    try:
        skill = parse_skill(req.definition)
    except SkillValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"valid": True, "normalized": skill_to_dict(skill)}


# ── Run endpoint (SSE stream) ────────────────────────────────────────────────


def _format_sse(event: SkillEvent) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.payload)}\n\n"


@router.post("/{skill_id}/run")
async def run_skill(
    skill_id: str,
    req: Annotated[SkillRunRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """Execute skill, stream events via SSE.

    Dispatcher = ``dispatch_agent_job`` di worker_ws.
    Agent resolver = ``UserAgentConfigRepository.agent_for_role``.
    """
    user_id = _resolve_user_id(authorization)

    with _session_factory()() as session:
        repo = ControlPlaneRepository(session)
        row = repo.get_skill(skill_id, user_id)
        if row is None:
            raise HTTPException(404, f"Skill {skill_id} tidak ditemukan")
        skill = repo.load_skill_domain(row)

    # Production wiring: dispatcher & resolver tidak di-inject ke router supaya
    # endpoint tetap simple. Untuk test, kita patch endpoint ini lewat factory
    # override (lihat ``tests/interfaces/test_skills_endpoints.py``).
    from app.interfaces.worker_ws import dispatch_agent_job
    user_agent_repo = UserAgentConfigRepository(_session_factory())
    executor = SkillExecutor(
        dispatcher=dispatch_agent_job,
        agent_resolver=user_agent_repo.agent_for_role,
    )

    from collections.abc import AsyncIterator as _AsyncIterator

    async def stream() -> _AsyncIterator[str]:
        async for ev in executor.execute(skill, user_id=user_id, base_prompt=req.prompt):
            yield _format_sse(ev)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
