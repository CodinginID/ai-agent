"""HTTP endpoints untuk workflow agentik architect→engineer→reviewer (issue #6).

Auth: Bearer session token (sama seperti ``context``/``skills``).

Endpoints:
- ``POST /workflow/plan``        — architect bikin Plan (body: goal)
- ``POST /workflow/implement``   — engineer→reviewer loop (body: plan_id)
- ``POST /workflow/review_last`` — re-review patch terakhir (body: plan_id)
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from app.adapters.sessions import UserSessionRepository
from app.composition import _session_factory, build_workflow_orchestrator
from app.domain.workflow import HallucinatedPathError, WorkflowError
from app.orchestrator.workflow import WorkflowOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflow", tags=["workflow"])


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


def _orchestrator() -> WorkflowOrchestrator:
    return build_workflow_orchestrator()


class PlanRequest(BaseModel):
    goal: str


class PlanIdRequest(BaseModel):
    plan_id: str


@router.post("/plan")
def make_plan(
    req: Annotated[PlanRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _resolve_user_id(authorization)
    goal = req.goal.strip()
    if not goal:
        raise HTTPException(status_code=400, detail="goal is empty")
    plan = _orchestrator().plan(goal, trace_id=str(uuid4()))
    return plan.__dict__


@router.post("/implement")
def implement(
    req: Annotated[PlanIdRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _resolve_user_id(authorization)
    try:
        result = _orchestrator().implement_and_review(req.plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HallucinatedPathError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "stage": str(result.stage),
        "revisions": result.revisions,
        "approved": result.verdict.approved,
        "patch": result.patch.__dict__,
        "verdict": result.verdict.__dict__,
    }


@router.post("/review_last")
def review_last(
    req: Annotated[PlanIdRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _resolve_user_id(authorization)
    try:
        verdict = _orchestrator().review_latest(req.plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return verdict.__dict__
