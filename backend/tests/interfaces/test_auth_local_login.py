# tests/interfaces/test_auth_local_login.py
from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.interfaces import auth as auth_module
from app.interfaces.auth import router


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)


def _set_google_oauth(monkeypatch: pytest.MonkeyPatch, *, configured: bool) -> None:
    monkeypatch.setattr(
        auth_module,
        "settings",
        dataclasses.replace(
            auth_module.settings,
            google_client_id="google-client-id" if configured else "",
            google_client_secret="google-client-secret" if configured else "",
        ),
    )


def _make_pair_code() -> str:
    code = auth_module._new_pair_code()
    auth_module._pair_codes[code] = auth_module._PairCode(
        created_at=auth_module.datetime.now(auth_module.UTC)
    )
    return code


def test_local_login_page_returns_404_when_google_oauth_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_google_oauth(monkeypatch, configured=True)
    code = _make_pair_code()

    resp = client.get(f"/auth/tui-local-login?code={code}")

    assert resp.status_code == 404


def test_local_login_submit_returns_404_when_google_oauth_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_google_oauth(monkeypatch, configured=True)
    code = _make_pair_code()

    resp = client.post(
        "/auth/tui-local-login/submit",
        data={"code": code, "name": "Someone Else", "email": "victim@example.com"},
    )

    assert resp.status_code == 404


def test_local_login_page_works_when_google_oauth_not_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_google_oauth(monkeypatch, configured=False)
    code = _make_pair_code()

    resp = client.get(f"/auth/tui-local-login?code={code}")

    assert resp.status_code != 404
    assert resp.status_code == 200


def test_local_login_submit_works_when_google_oauth_not_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.adapters.database.models import Base

    _set_google_oauth(monkeypatch, configured=False)
    code = _make_pair_code()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(auth_module, "_session_factory_lazy", lambda: factory)

    resp = client.post(
        "/auth/tui-local-login/submit",
        data={"code": code, "name": "Local User", "email": "local@octopus.internal"},
    )

    assert resp.status_code != 404
    assert resp.status_code == 200
