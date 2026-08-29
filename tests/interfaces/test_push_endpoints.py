"""HTTP tests for /push/* -- subscribe/unsubscribe/vapid-public-key/test.

Auth resolution (_resolve_caller / _resolve_user_and_conv) is exercised via
monkeypatch the same way tests/interfaces/test_tasks_endpoints.py does --
these helpers already have their own coverage; here we prove the push router
contract: 401 without auth, 503 when unconfigured, subscribe/unsubscribe
persist through the real adapter port (a fake push double), bad endpoint
rejected, and /push/test reports delivered count.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import load_settings
from app.interfaces import push as push_iface
from app.ports.push import PushMessage, PushSubscription

USER = "user-1"


class FakePush:
    def __init__(self) -> None:
        self.subscribed: list[tuple[str, PushSubscription]] = []
        self.unsubscribed: list[tuple[str, str]] = []
        self.notified: list[tuple[str, PushMessage]] = []
        self.deliver_count = 1

    async def subscribe(self, user_id: str, sub: PushSubscription) -> None:
        self.subscribed.append((user_id, sub))

    async def unsubscribe(self, user_id: str, endpoint: str) -> None:
        self.unsubscribed.append((user_id, endpoint))

    async def notify(self, user_id: str, msg: PushMessage) -> int:
        self.notified.append((user_id, msg))
        return self.deliver_count

    def is_configured(self) -> bool:
        return True


@pytest.fixture
def fake() -> FakePush:
    return FakePush()


@pytest.fixture
def client(fake: FakePush, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    configured = dataclasses.replace(
        load_settings(),
        vapid_public_key="pub-key-123",
        vapid_private_key="priv-key-123",
    )
    monkeypatch.setattr(push_iface, "settings", configured)
    monkeypatch.setattr(push_iface, "build_push", lambda: fake)
    monkeypatch.setattr(push_iface, "_resolve_caller", lambda _a: (USER, "user"))
    monkeypatch.setattr(push_iface, "_resolve_user_and_conv", lambda _a, _e: (USER, USER))
    app = FastAPI()
    app.include_router(push_iface.router)
    yield TestClient(app)


# -- auth ----------------------------------------------------------------------


def test_vapid_key_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without monkeypatched auth, the real _resolve_caller 401s (no Bearer)."""
    app = FastAPI()
    app.include_router(push_iface.router)
    client = TestClient(app)
    assert client.get("/push/vapid-public-key").status_code == 401


def test_subscribe_requires_auth() -> None:
    app = FastAPI()
    app.include_router(push_iface.router)
    client = TestClient(app)
    resp = client.post(
        "/push/subscribe",
        json={"endpoint": "https://push.example/x", "keys": {"p256dh": "a", "auth": "b"}},
    )
    assert resp.status_code == 401


# -- 503 when unconfigured ------------------------------------------------------


def test_vapid_key_503_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(push_iface, "_resolve_caller", lambda _a: (USER, "user"))
    monkeypatch.setattr(
        push_iface,
        "settings",
        dataclasses.replace(load_settings(), vapid_public_key="", vapid_private_key=""),
    )  # blank vapid keys
    app = FastAPI()
    app.include_router(push_iface.router)
    client = TestClient(app)
    resp = client.get("/push/vapid-public-key", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 503
    assert "belum dikonfigurasi" in resp.json()["detail"]


def test_subscribe_503_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(push_iface, "_resolve_user_and_conv", lambda _a, _e: (USER, USER))
    monkeypatch.setattr(
        push_iface,
        "settings",
        dataclasses.replace(load_settings(), vapid_public_key="", vapid_private_key=""),
    )
    app = FastAPI()
    app.include_router(push_iface.router)
    client = TestClient(app)
    resp = client.post(
        "/push/subscribe",
        json={"endpoint": "https://push.example/x", "keys": {"p256dh": "a", "auth": "b"}},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 503


# -- happy paths -----------------------------------------------------------------


def test_vapid_key_returned(client: TestClient) -> None:
    resp = client.get("/push/vapid-public-key", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    assert resp.json() == {"key": "pub-key-123"}


def test_subscribe_stores_under_resolved_user(client: TestClient, fake: FakePush) -> None:
    resp = client.post(
        "/push/subscribe",
        json={
            "endpoint": "https://push.example/abc",
            "keys": {"p256dh": "p256", "auth": "auth"},
            "as_email": "demo@local",
        },
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert len(fake.subscribed) == 1
    user_id, sub = fake.subscribed[0]
    assert user_id == USER
    assert sub.endpoint == "https://push.example/abc"
    assert sub.p256dh == "p256"


def test_subscribe_rejects_non_https_endpoint(client: TestClient, fake: FakePush) -> None:
    resp = client.post(
        "/push/subscribe",
        json={"endpoint": "http://insecure.example/abc", "keys": {"p256dh": "a", "auth": "b"}},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 400
    assert fake.subscribed == []


def test_unsubscribe(client: TestClient, fake: FakePush) -> None:
    resp = client.post(
        "/push/unsubscribe",
        json={"endpoint": "https://push.example/abc"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert fake.unsubscribed == [(USER, "https://push.example/abc")]


def test_push_test_returns_delivered_count(client: TestClient, fake: FakePush) -> None:
    fake.deliver_count = 3
    resp = client.post("/push/test", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    assert resp.json() == {"delivered": 3}
    assert len(fake.notified) == 1
    user_id, msg = fake.notified[0]
    assert user_id == USER
    assert msg.kind == "test"
