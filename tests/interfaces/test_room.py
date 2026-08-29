"""Room read-model endpoints + RoomBus (Fase 3 P2)."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.interfaces.chat as chat_mod
from app.config import load_settings
from app.interfaces.room import RoomBus, _bus, publish_room_event, router


class _FakeRoster:
    """Roster fake deterministik -- lepas dari Redis/DB nyata di test env."""

    async def list(self, user_id: str) -> list[object]:
        from app.ports.roster import DEFAULT_ROSTER

        return list(DEFAULT_ROSTER)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        chat_mod, "settings", dataclasses.replace(load_settings(), admin_token="test-admin")
    )
    import app.interfaces.room as room_mod

    monkeypatch.setattr(room_mod, "build_roster", lambda: _FakeRoster())
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_room_state_requires_auth(client: TestClient) -> None:
    assert client.get("/room/state").status_code == 401


def test_room_state_returns_roster(client: TestClient) -> None:
    r = client.get("/room/state", headers={"Authorization": "Bearer test-admin"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "room.snapshot"
    ids = {a["id"] for a in body["agents"]}
    assert "octo" in ids
    assert len(body["agents"]) == 7
    assert all(a["status"] == "idle" for a in body["agents"])


def test_roombus_pubsub_delivers_event() -> None:
    async def go() -> dict:
        bus = RoomBus()
        q = bus.subscribe()
        bus.publish({"type": "x", "v": 1})
        return await asyncio.wait_for(q.get(), timeout=1.0)

    assert asyncio.run(go()) == {"type": "x", "v": 1}


def test_publish_room_event_reaches_subscriber() -> None:
    async def go() -> dict:
        q = _bus.subscribe()
        try:
            publish_room_event("agent.status", id="octo", status="working")
            return await asyncio.wait_for(q.get(), timeout=1.0)
        finally:
            _bus.unsubscribe(q)

    ev = asyncio.run(go())
    assert ev["type"] == "agent.status"
    assert ev["status"] == "working"


def test_chat_mirror_publishes_room_activity() -> None:
    import app.interfaces.chat as chat_mod
    from app.domain.messaging import ChatEvent

    async def go() -> list[dict]:
        q = _bus.subscribe()
        try:
            chat_mod._mirror_to_room(ChatEvent.final("done"))
            # FINAL publish 2 event: agent.status(idle) + activity(done)
            return [await asyncio.wait_for(q.get(), timeout=1.0) for _ in range(2)]
        finally:
            _bus.unsubscribe(q)

    evs = asyncio.run(go())
    types = {e["type"] for e in evs}
    assert "agent.status" in types
    assert "activity" in types


# ── RoomTaskObserver push (Web Push saat task selesai) ────────────────────────

class _FakePush:
    def __init__(self, *, raise_on_notify: bool = False) -> None:
        self.calls: list[tuple[str, str, str]] = []  # (user_id, tag, body)
        self._raise = raise_on_notify

    async def subscribe(self, user_id: str, sub: object) -> None:
        return None

    async def unsubscribe(self, user_id: str, endpoint: str) -> None:
        return None

    async def notify(self, user_id: str, msg: object) -> int:
        if self._raise:
            raise RuntimeError("push kaboom")
        self.calls.append((user_id, msg.tag, msg.body))  # type: ignore[attr-defined]
        return 1

    def is_configured(self) -> bool:
        return True


class _NullInner:
    def task_started(self, task_id: str, user_id: str, request: str) -> None:
        return None

    def issue_opened(self, task_id: str, issue_number: int, issue_url: str) -> None:
        return None

    def step_started(self, task_id: str, order: int, role: str, description: str) -> None:
        return None

    def step_finished(self, task_id: str, order: int, role: str, ok: bool, detail: str) -> None:
        return None

    def task_finished(self, task_id: str, *, closed: bool, ok: bool, note: str) -> None:
        return None


def test_room_task_observer_pushes_to_user_from_task_started() -> None:
    from app.interfaces.room import RoomTaskObserver

    async def go() -> _FakePush:
        push = _FakePush()
        obs = RoomTaskObserver(_NullInner(), push=push)
        obs.task_started("t1", "user-42", "kerjakan sesuatu")
        obs.task_finished("t1", closed=True, ok=True, note="beres semua")
        await asyncio.sleep(0)  # let the fire-and-forget push task run
        return push

    push = asyncio.run(go())
    assert push.calls == [("user-42", "task-t1", "Tugas selesai: beres semua")]


def test_room_task_observer_cleans_task_user_mapping() -> None:
    from app.interfaces.room import RoomTaskObserver

    async def go() -> RoomTaskObserver:
        obs = RoomTaskObserver(_NullInner(), push=_FakePush())
        obs.task_started("t2", "user-9", "req")
        obs.task_finished("t2", closed=True, ok=True, note="ok")
        await asyncio.sleep(0)
        return obs

    obs = asyncio.run(go())
    assert "t2" not in obs._task_users


def test_room_task_observer_push_exception_does_not_propagate() -> None:
    from app.interfaces.room import RoomTaskObserver

    async def go() -> None:
        obs = RoomTaskObserver(_NullInner(), push=_FakePush(raise_on_notify=True))
        obs.task_started("t3", "user-1", "req")
        obs.task_finished("t3", closed=False, ok=False, note="gagal total")
        await asyncio.sleep(0)  # let the failing push task run & be swallowed

    asyncio.run(go())  # must not raise
