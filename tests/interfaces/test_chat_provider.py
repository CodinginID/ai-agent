"""Provider validation on /chat/send (BYOK persist path) — includes CLI providers."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.interfaces import chat as chat_iface

USER = "user-1"


class _FakeProviderRepo:
    """Stands in for ``UserProviderConfigRepository`` — no real DB needed here,
    this test only cares about validation, not persistence (that's covered by
    tests/adapters/test_user_provider_config.py)."""

    def __init__(self, factory: object) -> None:
        self.sets: list[tuple[str, str]] = []

    def set(self, user_id: str, provider: str, model: str | None = None) -> None:
        self.sets.append((user_id, provider))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    import app.adapters.user_provider_config as upc_mod

    monkeypatch.setattr(chat_iface, "_resolve_caller", lambda _a: (USER, "user"))
    monkeypatch.setattr(upc_mod, "UserProviderConfigRepository", _FakeProviderRepo)

    def _fake_stream_events(text, ctx, personal_key=None):  # type: ignore[no-untyped-def]
        async def gen():  # type: ignore[no-untyped-def]
            yield "event: done\ndata: {}\n\n"

        return gen()

    monkeypatch.setattr(chat_iface, "_stream_events", _fake_stream_events)
    app = FastAPI()
    app.include_router(chat_iface.router)
    yield TestClient(app)


def test_invalid_provider_rejected(client: TestClient) -> None:
    resp = client.post("/chat/send", json={"text": "hi", "provider": "gpt4"})
    assert resp.status_code == 400
    assert "provider" in resp.json()["detail"]


@pytest.mark.parametrize("provider", ["mock", "anthropic", "glm", "claude-cli", "glm-cli"])
def test_all_allowed_providers_accepted(client: TestClient, provider: str) -> None:
    resp = client.post("/chat/send", json={"text": "hi", "provider": provider})
    assert resp.status_code == 200
