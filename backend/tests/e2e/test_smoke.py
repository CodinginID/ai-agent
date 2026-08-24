"""Smoke tests untuk FastAPI gateway endpoints.

Menjalankan smoke tests sebelum deploy ke memastikan endpoints kritis
tidak down. Menggunakan baik httpx.AsyncClient (async) maupun TestClient
(sync) untuk cover kedua paradigma.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.interfaces.gateway import app

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client() -> TestClient:
    """Sync TestClient — bagus untuk endpoint yang tidak pakai async def."""
    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncClient:
    """Async httpx client dengan ASGITransport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Async tests (httpx.AsyncClient) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient) -> None:
    """GET /health → 200 dan response punya key 'status'."""
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body


@pytest.mark.asyncio
async def test_health_enhanced(async_client: AsyncClient) -> None:
    """GET /health → response lengkap: dependencies + details."""
    resp = await async_client.get("/health")
    body = resp.json()
    assert "dependencies" in body
    assert "details" in body
    # dependencies harus dict, details harus dict
    assert isinstance(body["dependencies"], dict)
    assert isinstance(body["details"], dict)


@pytest.mark.asyncio
async def test_metrics_endpoint(async_client: AsyncClient) -> None:
    """GET /metrics → 200 dan content type text/plain."""
    resp = await async_client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_swagger_ui(async_client: AsyncClient) -> None:
    """GET /docs → 200 (Swagger UI harus render)."""
    resp = await async_client.get("/docs")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_page(async_client: AsyncClient) -> None:
    """GET /auth/login → 200 atau 503 (503 jika OAuth belum dikonfigurasi)."""
    resp = await async_client.get("/auth/login")
    assert resp.status_code in (200, 503)


@pytest.mark.asyncio
async def test_chat_send_unauthorized(async_client: AsyncClient) -> None:
    """POST /chat/send tanpa Authorization header → 401."""
    resp = await async_client.post(
        "/chat/send",
        json={"text": "hello"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_send_empty(async_client: AsyncClient) -> None:
    """POST /chat/send dengan text kosong → 400."""
    # Bearer dummy + text kosong (atau whitespace)
    resp = await async_client.post(
        "/chat/send",
        json={"text": ""},
        headers={"Authorization": "Bearer fake-token"},
    )
    assert resp.status_code == 400


# ── Sync tests (TestClient) ─────────────────────────────────────────────────

def test_metrics_sync(client: TestClient) -> None:
    """Verifikasi metrics juga jalan via TestClient (sync path)."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_swagger_sync(client: TestClient) -> None:
    """Verifikasi /docs juga jalan via TestClient (sync path)."""
    resp = client.get("/docs")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_openapi_json(async_client: AsyncClient) -> None:
    """GET /openapi.json → 200 dan response JSON valid."""
    resp = await async_client.get("/openapi.json")
    assert resp.status_code == 200
    assert "openapi" in resp.json()
