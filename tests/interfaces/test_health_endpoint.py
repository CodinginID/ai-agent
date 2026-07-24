"""Tests for the enriched /health endpoint.

Health aggregates best-effort dependency checks (redis, ollama, database) and a
baked version string. Each dependency probe is monkeypatched so the test never
touches real infra; this proves the HTTP contract and the degraded-vs-ok logic.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.interfaces import health as health_iface


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    async def _ok_redis() -> bool:
        return True

    async def _ok_ollama() -> bool:
        return True

    async def _ok_db() -> bool:
        return True

    monkeypatch.setattr(health_iface, "_check_redis", _ok_redis)
    monkeypatch.setattr(health_iface, "_check_ollama", _ok_ollama)
    monkeypatch.setattr(health_iface, "_check_database", _ok_db)
    monkeypatch.setattr(health_iface, "_version", lambda: "abc1234")

    app = FastAPI()
    app.include_router(health_iface.router)
    yield TestClient(app)


def test_health_ok_when_all_deps_up(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "abc1234"
    assert body["dependencies"] == {"redis": "ok", "ollama": "ok", "database": "ok"}


def test_health_degraded_when_a_dep_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ok() -> bool:
        return True

    async def _down() -> bool:
        return False

    monkeypatch.setattr(health_iface, "_check_redis", _ok)
    monkeypatch.setattr(health_iface, "_check_ollama", _down)
    monkeypatch.setattr(health_iface, "_check_database", _ok)
    monkeypatch.setattr(health_iface, "_version", lambda: "v1")

    app = FastAPI()
    app.include_router(health_iface.router)
    c = TestClient(app)

    body = c.get("/health").json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["ollama"] == "down"


def test_health_never_raises_on_probe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom() -> bool:
        raise RuntimeError("connection refused")

    async def _ok() -> bool:
        return True

    monkeypatch.setattr(health_iface, "_check_redis", _boom)
    monkeypatch.setattr(health_iface, "_check_ollama", _ok)
    monkeypatch.setattr(health_iface, "_check_database", _ok)
    monkeypatch.setattr(health_iface, "_version", lambda: "v1")

    app = FastAPI()
    app.include_router(health_iface.router)
    c = TestClient(app)

    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["dependencies"]["redis"] == "down"
