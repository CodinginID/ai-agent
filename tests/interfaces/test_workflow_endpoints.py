from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.domain.workflow import (
    LoopLimitExceededError,
    Patch,
    PatchValidationError,
    Plan,
    Stage,
    Verdict,
)
from app.interfaces import workflow as wf
from app.orchestrator.workflow import WorkflowResult

USER = "user-1"


class FakeOrchestrator:
    def __init__(self) -> None:
        self.raise_on_implement: Exception | None = None

    def plan(self, goal: str, trace_id: str, context: str = "") -> Plan:
        return Plan(plan_id="p1", trace_id=trace_id, goal=goal, steps=("s",),
                    target_files=("app/main.py",), author_model="glm")

    def implement_and_review(self, plan_id: str) -> WorkflowResult:
        if self.raise_on_implement is not None:
            raise self.raise_on_implement
        plan = Plan(plan_id=plan_id, trace_id="t1", goal="g", steps=("s",),
                    target_files=("app/main.py",), author_model="glm")
        patch = Patch(patch_id="pt1", plan_id=plan_id, trace_id="t1", summary="ok",
                      changed_files=("app/main.py",), diff="d", author_model="codex")
        verdict = Verdict(verdict_id="v1", patch_id="pt1", trace_id="t1", approved=True,
                          comments="lgtm", reviewer_model="claude")
        return WorkflowResult(plan, patch, verdict, Stage.APPROVED, 0)

    def review_latest(self, plan_id: str) -> Verdict:
        return Verdict(verdict_id="v2", patch_id="pt1", trace_id="t1", approved=False,
                       comments="needs work", reviewer_model="claude")


@pytest.fixture
def fake() -> FakeOrchestrator:
    return FakeOrchestrator()


@pytest.fixture
def client(fake: FakeOrchestrator, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(wf, "_orchestrator", lambda: fake)
    monkeypatch.setattr(wf, "_resolve_user_id", lambda _a: USER)
    app = FastAPI()
    app.include_router(wf.router)
    yield TestClient(app)


def test_resolve_user_id_raises_401_without_bearer() -> None:
    with pytest.raises(HTTPException) as exc:
        wf._resolve_user_id(None)
    assert exc.value.status_code == 401


def test_plan_returns_plan_with_id(client: TestClient) -> None:
    resp = client.post("/workflow/plan", json={"goal": "add health endpoint"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_id"] == "p1"
    assert body["goal"] == "add health endpoint"


def test_plan_empty_goal_rejected(client: TestClient) -> None:
    assert client.post("/workflow/plan", json={"goal": "  "}).status_code == 400


def test_implement_returns_approved_result(client: TestClient) -> None:
    resp = client.post("/workflow/implement", json={"plan_id": "p1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved"] is True
    assert body["stage"] == "approved"
    assert body["patch"]["patch_id"] == "pt1"


def test_implement_unknown_plan_404(client: TestClient, fake: FakeOrchestrator) -> None:
    fake.raise_on_implement = KeyError("Plan 'x' tidak ditemukan")
    assert client.post("/workflow/implement", json={"plan_id": "x"}).status_code == 404


def test_implement_workflow_error_409(client: TestClient, fake: FakeOrchestrator) -> None:
    fake.raise_on_implement = PatchValidationError("bad patch")
    assert client.post("/workflow/implement", json={"plan_id": "p1"}).status_code == 409


def test_implement_loop_cap_409(client: TestClient, fake: FakeOrchestrator) -> None:
    fake.raise_on_implement = LoopLimitExceededError("cap")
    assert client.post("/workflow/implement", json={"plan_id": "p1"}).status_code == 409


def test_review_last_returns_verdict(client: TestClient) -> None:
    resp = client.post("/workflow/review_last", json={"plan_id": "p1"})
    assert resp.status_code == 200
    assert resp.json()["approved"] is False
    assert resp.json()["comments"] == "needs work"
