"""HTTP endpoints untuk project context memory (issue #9).

Per-user context (notes/decisions/tasks) yang di-inject ke prompt chat supaya
Qwen bisa menjawab dengan konteks project tanpa user mengulang-ulang.

Auth: Bearer session token (dari TUI login flow) — sama seperti ``skills``.
Context disimpan per ``user_id`` lewat ``ProjectContextStore``.

Endpoints:
- ``POST /context/remember``        — simpan catatan bebas (body: text)
- ``POST /context/decision``        — catat keputusan (body: text)
- ``GET  /context/tasks``           — daftar task
- ``POST /context/tasks``           — tambah task (body: text)
- ``POST /context/tasks/{id}/done`` — tandai task selesai
- ``GET  /context``                 — ringkasan konteks + daftar terstruktur
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from app.adapters.sessions import UserSessionRepository
from app.composition import _context_store, _session_factory
from app.memory.context_store import ProjectContextStore, TaskNotFoundError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/context", tags=["context"])


def _resolve_user_id(authorization: str | None) -> str:
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


def _store() -> ProjectContextStore:
    return _context_store()


class TextRequest(BaseModel):
    text: str


def _require_text(req: TextRequest) -> str:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    return text


@router.post("/remember")
def remember(
    req: Annotated[TextRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    note = _store().add_note(user_id, _require_text(req))
    return note.__dict__


@router.post("/decision")
def decision(
    req: Annotated[TextRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    result = _store().add_decision(user_id, _require_text(req))
    return result.__dict__


@router.get("/tasks")
def list_tasks(authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    user_id = _resolve_user_id(authorization)
    return [t.__dict__ for t in _store().list_tasks(user_id)]


@router.post("/tasks")
def add_task(
    req: Annotated[TextRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    task = _store().add_task(user_id, _require_text(req))
    return task.__dict__


@router.post("/tasks/{task_id}/done")
def complete_task(
    task_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    try:
        task = _store().complete_task(user_id, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return task.__dict__


@router.get("")
def get_context(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    store = _store()
    open_tasks = [t.__dict__ for t in store.list_tasks(user_id) if t.status == "open"]
    decisions = [d.__dict__ for d in store.list_decisions(user_id, limit=10)]
    notes = [n.__dict__ for n in store.list_notes(user_id, limit=10)]
    return {
        "summary": store.build_context(user_id),
        "open_tasks": open_tasks,
        "decisions": decisions,
        "notes": notes,
    }
