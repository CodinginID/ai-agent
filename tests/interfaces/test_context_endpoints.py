from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.interfaces import context as context_module
from app.memory.context_store import ProjectContextStore

USER = "user-1"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    store = ProjectContextStore(tmp_path)
    monkeypatch.setattr(context_module, "_store", lambda: store)
    monkeypatch.setattr(context_module, "_resolve_user_id", lambda _auth: USER)

    app = FastAPI()
    app.include_router(context_module.router)
    yield TestClient(app)


# ── auth helper ──────────────────────────────────────────────────────────────


def test_resolve_user_id_raises_401_without_bearer() -> None:
    with pytest.raises(HTTPException) as exc:
        context_module._resolve_user_id(None)
    assert exc.value.status_code == 401


# ── notes / decisions ────────────────────────────────────────────────────────


def test_remember_creates_note(client: TestClient) -> None:
    resp = client.post("/context/remember", json={"text": "domain prod: example.com"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "domain prod: example.com"
    assert resp.json()["id"]


def test_decision_creates_decision(client: TestClient) -> None:
    resp = client.post("/context/decision", json={"text": "pakai Postgres"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "pakai Postgres"


def test_empty_text_is_rejected(client: TestClient) -> None:
    resp = client.post("/context/remember", json={"text": "   "})
    assert resp.status_code == 400


# ── tasks ────────────────────────────────────────────────────────────────────


def test_add_and_list_tasks(client: TestClient) -> None:
    client.post("/context/tasks", json={"text": "deploy staging"})
    client.post("/context/tasks", json={"text": "fix login"})
    rows = client.get("/context/tasks").json()
    assert [t["text"] for t in rows] == ["deploy staging", "fix login"]
    assert rows[0]["status"] == "open"


def test_complete_task(client: TestClient) -> None:
    task = client.post("/context/tasks", json={"text": "a"}).json()
    resp = client.post(f"/context/tasks/{task['id']}/done")
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"


def test_complete_unknown_task_returns_404(client: TestClient) -> None:
    resp = client.post("/context/tasks/999/done")
    assert resp.status_code == 404


# ── context summary ──────────────────────────────────────────────────────────


def test_get_context_returns_summary_and_lists(client: TestClient) -> None:
    client.post("/context/decision", json={"text": "pakai Redis"})
    client.post("/context/tasks", json={"text": "tulis docs"})
    body = client.get("/context").json()
    assert "pakai Redis" in body["summary"]
    assert "tulis docs" in body["summary"]
    assert len(body["open_tasks"]) == 1
    assert len(body["decisions"]) == 1
