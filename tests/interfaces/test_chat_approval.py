# tests/interfaces/test_chat_approval.py
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.interfaces.gateway import app as gateway_app
import app.interfaces.chat as chat_mod


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        chat_mod, "_resolve_caller", lambda auth: ("user@example.com", "session")
    )
    return TestClient(gateway_app)


def _pending(intent: str = "docker_compose_restart") -> SimpleNamespace:
    return SimpleNamespace(
        plan=SimpleNamespace(plan_id="abc123", intent=intent),
        chat_id=0,
        user_text="restart service",
        action_context={"service": "web"},
        expires_at=datetime.now() + timedelta(minutes=5),
    )


def test_approve_unknown_plan_streams_error(client, monkeypatch):
    monkeypatch.setattr(
        chat_mod.pending_plans, "consume", lambda plan_id, chat_id: None
    )
    resp = client.post(
        "/chat/approve",
        json={"plan_id": "nope"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert "event: error" in resp.text


def test_approve_executes_action_and_streams_result(client, monkeypatch):
    monkeypatch.setattr(
        chat_mod.pending_plans, "consume", lambda plan_id, chat_id: _pending()
    )
    monkeypatch.setattr(
        chat_mod.action_registry, "execute", lambda name, ctx: "service restarted"
    )
    resp = client.post(
        "/chat/approve",
        json={"plan_id": "abc123"},
        headers={"Authorization": "Bearer x"},
    )
    body = resp.text
    assert "event: action_started" in body
    assert "event: action_result" in body
    assert "service restarted" in body
    assert "event: final" in body
    assert "event: done" in body


def test_approve_action_failure_streams_error_and_closes(client, monkeypatch):
    monkeypatch.setattr(
        chat_mod.pending_plans, "consume", lambda plan_id, chat_id: _pending()
    )

    def _boom(name, ctx):
        raise Exception("boom")

    monkeypatch.setattr(chat_mod.action_registry, "execute", _boom)
    resp = client.post(
        "/chat/approve",
        json={"plan_id": "abc123"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert "event: error" in resp.text
    assert "event: done" in resp.text


def test_reject_cancels_plan(client, monkeypatch):
    monkeypatch.setattr(
        chat_mod.pending_plans, "cancel", lambda plan_id, chat_id: True
    )
    resp = client.post(
        "/chat/reject",
        json={"plan_id": "abc123"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_reject_unknown_plan_returns_ok_false(client, monkeypatch):
    monkeypatch.setattr(
        chat_mod.pending_plans, "cancel", lambda plan_id, chat_id: False
    )
    resp = client.post(
        "/chat/reject",
        json={"plan_id": "zzz"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.json() == {"ok": False}
