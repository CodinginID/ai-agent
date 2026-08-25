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


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        chat_mod, "settings", dataclasses.replace(load_settings(), admin_token="test-admin")
    )
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
