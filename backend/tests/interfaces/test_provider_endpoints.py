# tests/interfaces/test_provider_endpoints.py
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.database.models import Base, UserModel
from app.interfaces import provider as provider_module
from app.interfaces.provider import router


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr("app.interfaces.provider._resolve_session_user", lambda auth: ("u1", "user"))

    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)

    with factory() as s:
        s.add(UserModel(id="u1", email="a@b.c"))
        s.commit()

    monkeypatch.setattr(provider_module, "_session_factory", lambda: factory)

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)


def test_get_provider_default(client: TestClient) -> None:
    resp = client.get("/provider")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "ollama"
    assert data["is_default"] is True


def test_set_and_get_provider(client: TestClient) -> None:
    resp = client.post("/provider", json={"provider": "anthropic", "model": "claude-opus-4-8"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    resp = client.get("/provider")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-opus-4-8"
    assert data["is_default"] is False


def test_set_invalid_provider_returns_400(client: TestClient) -> None:
    resp = client.post("/provider", json={"provider": "unknown_ai"})
    assert resp.status_code == 400
