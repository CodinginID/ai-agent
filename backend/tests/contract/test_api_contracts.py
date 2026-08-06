"""Contract tests: verify HTTP response shapes against expected schemas.

These tests focus on response structure (keys, value types) rather than
business content. They use FastAPI's TestClient with an in-process ASGI
application so they exercise the real serialization path without starting
a network listener.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient

from app.domain.messaging import ChatEvent, ChatEventType
from app.interfaces import auth as auth_module
from app.interfaces import health as health_module
from app.interfaces.metrics import get_metrics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_health_app(
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    """Health app with all probes stubbed to return 'ok'."""

    async def _ok_redis() -> bool:
        return True

    async def _ok_ollama() -> bool:
        return True

    async def _ok_db() -> bool:
        return True

    monkeypatch.setattr(health_module, "_check_redis", _ok_redis)
    monkeypatch.setattr(health_module, "_check_ollama", _ok_ollama)
    monkeypatch.setattr(health_module, "_check_database", _ok_db)
    monkeypatch.setattr(health_module, "_version", lambda: "abc1234")

    app = FastAPI()
    app.include_router(health_module.router)
    return app


def _build_auth_app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_token: str | None = None,
    google_configured: bool = False,
) -> FastAPI:
    """Auth-only app. Pass a session_token to simulate a logged-in user."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.adapters.database.models import Base, UserModel
    from app.adapters.sessions import UserSessionRepository

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        auth_module,
        "settings",
        dataclasses.replace(
            auth_module.settings,
            google_client_id="gid" if google_configured else "",
            google_client_secret="gsec" if google_configured else "",
        ),
    )

    app = FastAPI()
    app.include_router(auth_module.router)

    if session_token:
        factory = sessionmaker(engine)
        monkeypatch.setattr(auth_module, "_session_factory_lazy", lambda: factory)

        with factory() as session:
            user = session.scalar(session.query(UserModel).first())
            if user is None:
                user = UserModel(
                    display_name="Contract Tester",
                    email="contract@example.com",
                )
                session.add(user)
                session.flush()
            user_id = user.id

        sessions = UserSessionRepository(factory)
        info = sessions.create(user_id=user_id, user_agent="contract-test")
        monkeypatch.setattr(auth_module, "_resolve_session_user", lambda _auth: (info.user_id, info.token))

    return app


def _build_metrics_app() -> FastAPI:
    """App exposing only the /metrics endpoint."""
    app = FastAPI()

    @app.get("/metrics", response_class=Response)
    async def _metrics() -> Response:
        return Response(
            content=get_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


@pytest.fixture
def health_client(
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    return TestClient(_build_health_app(monkeypatch))


@pytest.fixture
def auth_client(
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    return TestClient(_build_auth_app(monkeypatch))


@pytest.fixture
def auth_logged_client(
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    return TestClient(
        _build_auth_app(monkeypatch, session_token="stub"),
        headers={"Authorization": "Bearer stub"},
    )


@pytest.fixture
def metrics_client() -> TestClient:
    return TestClient(_build_metrics_app())


# ---------------------------------------------------------------------------
# ChatEvent structure
# ---------------------------------------------------------------------------


def test_chat_event_structure_thinking() -> None:
    """ChatEvent(type, payload) with THINKING payload shape."""
    event = ChatEvent.thinking("I'm on it")
    assert event.type == ChatEventType.THINKING
    assert set(event.payload.keys()) == {"message"}
    assert isinstance(event.payload["message"], str)


def test_chat_event_structure_intent_classified() -> None:
    """ChatEvent for INTENT_CLASSIFIED must carry intent/confidence/reason."""
    event = ChatEvent.intent_classified(intent="server_status", confidence=0.95, reason="keyword match")
    assert event.type == ChatEventType.INTENT_CLASSIFIED
    required = {"intent", "confidence", "reason"}
    assert set(event.payload.keys()) == required
    assert isinstance(event.payload["intent"], str)
    assert isinstance(event.payload["confidence"], float)
    assert isinstance(event.payload["reason"], str)


def test_chat_event_structure_error() -> None:
    """ChatEvent for ERROR must carry message string."""
    event = ChatEvent.error("something broke")
    assert event.type == ChatEventType.ERROR
    assert set(event.payload.keys()) == {"message"}
    assert isinstance(event.payload["message"], str)


# ---------------------------------------------------------------------------
# /health response schema
# ---------------------------------------------------------------------------


def test_health_response_schema(health_client: TestClient) -> None:
    """/health returns 200 with status, version, dependencies, details."""
    resp = health_client.get("/health")
    assert resp.status_code == 200

    body = resp.json()
    required_top = {"status", "version", "dependencies", "details"}
    assert set(body.keys()) >= required_top, f"missing keys: {required_top - body.keys()}"

    assert isinstance(body["status"], str)
    assert body["status"] in {"ok", "degraded"}
    assert isinstance(body["version"], str)

    deps = body["dependencies"]
    assert isinstance(deps, dict)
    assert set(deps.keys()) >= {"redis", "ollama", "database"}
    for val in deps.values():
        assert val in {"ok", "down"}

    details = body["details"]
    assert isinstance(details, dict)
    for value in details.values():
        assert value is None or isinstance(value, (str, int))


# ---------------------------------------------------------------------------
# /metrics Prometheus text format
# ---------------------------------------------------------------------------


def test_metrics_response_format(metrics_client: TestClient) -> None:
    """/metrics returns 200 in text/plain with HELP/TYPE lines and metric values."""
    resp = metrics_client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")

    body = resp.text
    # Prometheus spec: # HELP and # TYPE comments plus metric lines with values.
    assert "# HELP" in body
    assert "# TYPE" in body
    # At least the active_workers gauge should be present (always emitted).
    assert "octopus_active_workers" in body


# ---------------------------------------------------------------------------
# /auth/me response schema
# ---------------------------------------------------------------------------


def test_auth_response_schema(auth_logged_client: TestClient) -> None:
    """/auth/me returns user_id, email, display_name."""
    resp = auth_logged_client.get("/auth/me")
    assert resp.status_code == 200

    body = resp.json()
    required = {"user_id", "email", "display_name"}
    missing = required - body.keys()
    assert not missing, f"missing keys: {missing}"

    # user_id is stored as a string (UUID) in the model.
    assert isinstance(body["user_id"], str)
    assert isinstance(body["email"], str)
    assert isinstance(body["display_name"], str)


# ---------------------------------------------------------------------------
# Error response schema
# ---------------------------------------------------------------------------


def test_error_response_schema(auth_client: TestClient) -> None:
    """/auth endpoints raise 4xx/5xx with a 'detail' key in the JSON body."""
    resp = auth_client.get("/auth/me")
    assert resp.status_code == 401

    body = resp.json()
    assert "detail" in body, f"expected 'detail' key, got: {body.keys()}"
    assert isinstance(body["detail"], str)


def test_error_response_schema_auth_bad_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """/auth/me with a token that resolves to nothing still returns 'detail' key."""

    async def _unresolved(_auth: str | None):
        return None

    monkeypatch.setattr(auth_module, "_resolve_session_user", _unresolved)

    app = _build_auth_app(monkeypatch, session_token="never-used")
    client = TestClient(
        app,
        headers={"Authorization": "Bearer never-used"},
    )

    resp = client.get("/auth/me")
    assert resp.status_code == 401
    body = resp.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)
