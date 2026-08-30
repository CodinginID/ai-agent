"""Tests for PUT /auth/me/provider — persist 'otak' choice, no side effects."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.interfaces.auth as auth_iface
import app.interfaces.chat as chat_iface

USER = "user-1"
ADMIN_EMAIL = "target@example.com"
ADMIN_USER_ID = "user-admin-target"


class _FakeProviderRepo:
    def __init__(self, factory: object) -> None:
        pass

    def set(self, user_id: str, provider: str, model: str | None = None) -> None:
        _CALLS.append((user_id, provider))


_CALLS: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def _reset_calls() -> Iterator[None]:
    _CALLS.clear()
    yield
    _CALLS.clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    import app.adapters.user_provider_config as upc_mod

    monkeypatch.setattr(upc_mod, "UserProviderConfigRepository", _FakeProviderRepo)
    monkeypatch.setattr(chat_iface, "_resolve_caller", lambda _a: (USER, "user"))
    monkeypatch.setattr(
        chat_iface, "_resolve_admin_target", lambda email: ADMIN_USER_ID if email == ADMIN_EMAIL else None
    )
    app = FastAPI()
    app.include_router(auth_iface.router)
    yield TestClient(app)


def test_set_provider_persists_for_session_user(client: TestClient) -> None:
    resp = client.put("/auth/me/provider", json={"provider": "claude-cli"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "provider": "claude-cli"}
    assert _CALLS == [(USER, "claude-cli")]


def test_invalid_provider_rejected(client: TestClient) -> None:
    resp = client.put("/auth/me/provider", json={"provider": "gpt4"})
    assert resp.status_code == 400
    assert _CALLS == []


@pytest.mark.parametrize("provider", ["mock", "anthropic", "glm", "claude-cli", "glm-cli"])
def test_all_allowed_providers_accepted(client: TestClient, provider: str) -> None:
    resp = client.put("/auth/me/provider", json={"provider": provider})
    assert resp.status_code == 200


def test_provider_case_and_whitespace_normalized(client: TestClient) -> None:
    resp = client.put("/auth/me/provider", json={"provider": "  Claude-CLI  "})
    assert resp.status_code == 200
    assert _CALLS == [(USER, "claude-cli")]


def test_admin_without_as_email_rejected(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(chat_iface, "_resolve_caller", lambda _a: ("__ADMIN__", "admin"))
    resp = client.put("/auth/me/provider", json={"provider": "mock"})
    assert resp.status_code == 400
    assert "as_email" in resp.json()["detail"]


def test_admin_sets_provider_for_target_user(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(chat_iface, "_resolve_caller", lambda _a: ("__ADMIN__", "admin"))
    resp = client.put(
        "/auth/me/provider", json={"provider": "glm-cli", "as_email": ADMIN_EMAIL}
    )
    assert resp.status_code == 200
    assert _CALLS == [(ADMIN_USER_ID, "glm-cli")]
