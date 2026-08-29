"""HTTP tests for /room/roster/* -- list/upsert/delete + roster.updated publish.

Auth resolution (_resolve_user_and_conv) sudah punya coverage sendiri di
tests/interfaces/test_chat*.py; di sini kita monkeypatch supaya fokus ke
kontrak router roster: 401 tanpa auth, validasi 400, larangan hapus manajer,
PUT membuat/mengubah, DELETE menghapus, dan publish roster.updated ke RoomBus.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.interfaces import roster as roster_iface
from app.ports.roster import DEFAULT_ROSTER, RosterAgent

USER = "user-1"


class FakeRoster:
    def __init__(self) -> None:
        self._agents: dict[str, RosterAgent] = {a.id: a for a in DEFAULT_ROSTER}

    async def list(self, user_id: str) -> list[RosterAgent]:
        return list(self._agents.values())

    async def upsert(self, user_id: str, agent: RosterAgent) -> None:
        self._agents[agent.id] = agent

    async def delete(self, user_id: str, agent_id: str) -> bool:
        return self._agents.pop(agent_id, None) is not None


@pytest.fixture
def fake() -> FakeRoster:
    return FakeRoster()


@pytest.fixture
def client(fake: FakeRoster, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(roster_iface, "build_roster", lambda: fake)
    monkeypatch.setattr(roster_iface, "_resolve_user_and_conv", lambda _a, _e: (USER, USER))
    app = FastAPI()
    app.include_router(roster_iface.router)
    yield TestClient(app)


# -- auth ----------------------------------------------------------------------


def test_list_requires_auth() -> None:
    app = FastAPI()
    app.include_router(roster_iface.router)
    resp = TestClient(app).get("/room/roster")
    assert resp.status_code == 401


def test_put_requires_auth() -> None:
    app = FastAPI()
    app.include_router(roster_iface.router)
    resp = TestClient(app).put("/room/roster/nadia", json={"name": "X", "role": "coder"})
    assert resp.status_code == 401


def test_delete_requires_auth() -> None:
    app = FastAPI()
    app.include_router(roster_iface.router)
    resp = TestClient(app).delete("/room/roster/nadia")
    assert resp.status_code == 401


# -- list ------------------------------------------------------------------------


def test_list_returns_default_roster(client: TestClient) -> None:
    resp = client.get("/room/roster", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == len(DEFAULT_ROSTER)
    assert {a["id"] for a in body} == {a.id for a in DEFAULT_ROSTER}


# -- validation --------------------------------------------------------------------


def test_put_rejects_invalid_id(client: TestClient) -> None:
    resp = client.put(
        "/room/roster/Invalid_ID!",
        json={"name": "X", "role": "coder"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 400


def test_put_rejects_empty_name(client: TestClient) -> None:
    resp = client.put(
        "/room/roster/nadia",
        json={"name": "   ", "role": "coder"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 400


def test_put_rejects_name_too_long(client: TestClient) -> None:
    resp = client.put(
        "/room/roster/nadia",
        json={"name": "x" * 25, "role": "coder"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 400


def test_put_rejects_unknown_role(client: TestClient) -> None:
    resp = client.put(
        "/room/roster/nadia",
        json={"name": "Nadia", "role": "ceo"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 400


# -- CRUD happy paths -----------------------------------------------------------


def test_put_creates_new_agent(client: TestClient, fake: FakeRoster) -> None:
    resp = client.put(
        "/room/roster/baru",
        json={"name": "Agen Baru", "role": "tester"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"id": "baru", "name": "Agen Baru", "role": "tester"}
    assert fake._agents["baru"].role == "tester"


def test_put_updates_existing_agent(client: TestClient, fake: FakeRoster) -> None:
    resp = client.put(
        "/room/roster/nadia",
        json={"name": "Nadia B.", "role": "reviewer"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert fake._agents["nadia"].name == "Nadia B."
    assert fake._agents["nadia"].role == "reviewer"


def test_delete_removes_agent(client: TestClient, fake: FakeRoster) -> None:
    resp = client.delete("/room/roster/nadia", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert "nadia" not in fake._agents


def test_delete_unknown_agent_returns_false(client: TestClient) -> None:
    resp = client.delete("/room/roster/nobody", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": False}


def test_cannot_delete_manager(client: TestClient, fake: FakeRoster) -> None:
    resp = client.delete("/room/roster/octo", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 400
    assert "octo" in fake._agents


# -- roster.updated publish ------------------------------------------------------


def test_put_publishes_roster_updated(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    published: list[dict[str, object]] = []
    monkeypatch.setattr(
        roster_iface,
        "_publish_roster_updated",
        lambda agents: published.append({"agents": [a.id for a in agents]}),
    )
    resp = client.put(
        "/room/roster/baru",
        json={"name": "Baru", "role": "coder"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert len(published) == 1
    assert "baru" in published[0]["agents"]


def test_delete_publishes_roster_updated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    published: list[dict[str, object]] = []
    monkeypatch.setattr(
        roster_iface,
        "_publish_roster_updated",
        lambda agents: published.append({"agents": [a.id for a in agents]}),
    )
    resp = client.delete("/room/roster/nadia", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    assert len(published) == 1
    assert "nadia" not in published[0]["agents"]
