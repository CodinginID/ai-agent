"""Endpoint tests for /tasks/run — wires the PM→Issue→Worker→Close runner.

The TaskRunner is replaced by a fake (so no real PM / GitHub / worker is hit);
auth is patched the same way the workflow endpoint tests do. This proves the
HTTP contract: a request runs the chain and the JSON result mirrors TaskResult.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.github import GitHubUnavailableError
from app.agents.pm import TaskPlan, TaskStep
from app.interfaces import tasks as tasks_iface
from app.orchestrator.task_runner import StepOutcome, TaskResult

USER = "user-1"


class FakeTaskRunner:
    def __init__(self) -> None:
        self.result: TaskResult | None = None
        self.calls: list[tuple[str, str, str]] = []

    async def run(self, user_id: str, request: str, context: str = "") -> TaskResult:
        self.calls.append((user_id, request, context))
        assert self.result is not None
        return self.result


def _plan() -> TaskPlan:
    return TaskPlan(
        title="Add health endpoint",
        summary="add a /health route with a test",
        steps=[TaskStep(order=1, description="write route", action="file_write", params={})],
        estimated_complexity="simple",
    )


@pytest.fixture
def fake() -> FakeTaskRunner:
    return FakeTaskRunner()


@pytest.fixture
def client(fake: FakeTaskRunner, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(tasks_iface, "build_task_runner", lambda: fake)
    monkeypatch.setattr(tasks_iface, "_resolve_caller", lambda _a: (USER, "user"))
    app = FastAPI()
    app.include_router(tasks_iface.router)
    yield TestClient(app)


def test_empty_request_rejected(client: TestClient) -> None:
    assert client.post("/tasks/run", json={"request": "  "}).status_code == 400


def test_run_returns_closed_task(client: TestClient, fake: FakeTaskRunner) -> None:
    plan = _plan()
    fake.result = TaskResult(
        plan=plan,
        issue_number=42,
        issue_url="https://github.com/o/r/issues/42",
        outcomes=[StepOutcome(order=1, description="write route", role="engineer", ok=True, detail="done")],
        closed=True,
        note="completed",
    )

    resp = client.post("/tasks/run", json={"request": "add health endpoint"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["issue_number"] == 42
    assert body["closed"] is True
    assert body["summary"] == "add a /health route with a test"
    assert body["outcomes"][0]["role"] == "engineer"
    assert fake.calls == [(USER, "add health endpoint", "")]


def test_run_passes_context(client: TestClient, fake: FakeTaskRunner) -> None:
    fake.result = TaskResult(plan=_plan(), issue_number=1, issue_url="u", outcomes=[
        StepOutcome(order=1, description="x", role="engineer", ok=True),
    ], closed=True)

    resp = client.post("/tasks/run", json={"request": "do x", "context": "repo foo"})

    assert resp.status_code == 200
    assert fake.calls[0][2] == "repo foo"


def test_run_failed_task_left_open(client: TestClient, fake: FakeTaskRunner) -> None:
    fake.result = TaskResult(
        plan=_plan(),
        issue_number=7,
        issue_url="https://github.com/o/r/issues/7",
        outcomes=[StepOutcome(order=1, description="write route", role="engineer", ok=False, detail="boom")],
        closed=False,
        note="stopped at step 1 (engineer): boom",
    )

    body = client.post("/tasks/run", json={"request": "x"}).json()

    assert body["ok"] is False
    assert body["closed"] is False
    assert "stopped at step 1" in body["note"]


def test_run_no_steps_no_issue(client: TestClient, fake: FakeTaskRunner) -> None:
    empty_plan = TaskPlan(title="", summary="nothing to do", steps=[], estimated_complexity="simple")
    fake.result = TaskResult(plan=empty_plan, issue_number=None, issue_url="", note="no steps to execute")

    body = client.post("/tasks/run", json={"request": "hi"}).json()

    assert body["ok"] is False
    assert body["issue_number"] is None
    assert body["outcomes"] == []


def test_run_503_when_github_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> object:
        raise GitHubUnavailableError("GITHUB_TOKEN tidak diisi.")

    monkeypatch.setattr(tasks_iface, "build_task_runner", _boom)
    resp = client.post("/tasks/run", json={"request": "x"})
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"]


def test_admin_requires_as_email(monkeypatch: pytest.MonkeyPatch, fake: FakeTaskRunner) -> None:
    monkeypatch.setattr(tasks_iface, "build_task_runner", lambda: fake)
    monkeypatch.setattr(tasks_iface, "_resolve_caller", lambda _a: ("__ADMIN__", "admin"))
    app = FastAPI()
    app.include_router(tasks_iface.router)
    c = TestClient(app)

    resp = c.post("/tasks/run", json={"request": "x"})
    assert resp.status_code == 400
    assert "as_email" in resp.json()["detail"]


# ── GET /tasks board (PR-5) ──────────────────────────────────────────────────


def test_board_returns_collapsed_tasks_and_events(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [
        {"id": "3-0", "task_id": "t1", "role": "pm", "status": "closed", "message": "done"},
        {"id": "2-0", "task_id": "t1", "role": "engineer", "status": "step_ok", "message": "x"},
        {"id": "1-0", "task_id": "t2", "role": "pm", "status": "started", "message": "y"},
    ]

    async def _fake_recent(limit: int = 100) -> list[dict[str, str]]:
        return events

    monkeypatch.setattr(tasks_iface, "_resolve_caller", lambda _a: (USER, "user"))
    import app.adapters.task_observer as obs_mod

    monkeypatch.setattr(obs_mod, "recent_task_events", _fake_recent)

    resp = client.get("/tasks/")
    assert resp.status_code == 200
    body = resp.json()
    # 3 raw events, collapsed to 2 tasks (t1 latest=closed, t2=started).
    assert len(body["events"]) == 3
    statuses = {t["task_id"]: t["status"] for t in body["tasks"]}
    assert statuses == {"t1": "closed", "t2": "started"}

