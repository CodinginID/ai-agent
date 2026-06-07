"""HTTP endpoint for the orchestrator task runner — PM→Issue→Worker→Close.

Flow:
1. Client POSTs ``/tasks/run`` with ``{"request": "...", "as_email": "x@y.com"}``.
2. Auth: same model as ``/chat/send`` — Bearer ADMIN_TOKEN (admin runs a task
   as user X via ``as_email``) or a session token (runs as that user).
3. Backend builds the ``TaskRunner`` via composition and runs the chain: PM
   decomposes the request → a GitHub Issue records it → each step dispatches to
   a worker (routed by role) → the issue is commented per step and closed on
   success.

Unlike ``/chat/send`` this returns a single JSON ``TaskResult`` (not SSE): a
task is a durable unit recorded in the issue, so the issue URL is the live view,
and the response is just the final summary.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from app.adapters.github import GitHubUnavailableError
from app.composition import build_task_runner
from app.interfaces.chat import _resolve_admin_target, _resolve_caller

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskRunRequest(BaseModel):
    request: str
    context: str = ""
    # Only used when the caller is the admin token (run a task as user X).
    as_email: str | None = None


class StepOutcomeOut(BaseModel):
    order: int
    description: str
    role: str
    ok: bool
    detail: str = ""


class TaskRunResponse(BaseModel):
    ok: bool
    issue_number: int | None
    issue_url: str
    closed: bool
    note: str
    summary: str
    outcomes: list[StepOutcomeOut]


@router.post("/run", response_model=TaskRunResponse)
async def run_task(
    req: Annotated[TaskRunRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> TaskRunResponse:
    request_text = req.request.strip()
    if not request_text:
        raise HTTPException(status_code=400, detail="request is empty")

    caller_user_id, mode = _resolve_caller(authorization)
    if mode == "admin":
        if not req.as_email:
            raise HTTPException(
                status_code=400,
                detail="admin token requires 'as_email' field",
            )
        user_id = _resolve_admin_target(req.as_email)
    else:
        user_id = caller_user_id

    try:
        runner = build_task_runner()
    except GitHubUnavailableError as exc:
        # Explicit, not silent — task tracking needs GitHub configured.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"task runner unavailable: {exc}",
        ) from exc

    result = await runner.run(user_id, request_text, req.context)

    return TaskRunResponse(
        ok=result.ok,
        issue_number=result.issue_number,
        issue_url=result.issue_url,
        closed=result.closed,
        note=result.note,
        summary=result.plan.summary,
        outcomes=[
            StepOutcomeOut(
                order=o.order,
                description=o.description,
                role=o.role,
                ok=o.ok,
                detail=o.detail,
            )
            for o in result.outcomes
        ],
    )
