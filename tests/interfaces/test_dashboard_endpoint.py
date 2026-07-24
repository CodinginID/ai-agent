"""Tests for the read-only web dashboard route.

The dashboard is a single self-contained HTML page served by FastAPI. It ships
no secrets: the browser supplies the admin token from localStorage and calls the
existing JSON APIs (/health, /tasks) client-side. These tests assert the route
serves HTML and that the shell references the data endpoints it polls.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.interfaces import dashboard as dash_iface


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(dash_iface.router)
    yield TestClient(app)


def test_dashboard_serves_html(client: TestClient) -> None:
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in resp.text or "<!doctype html>" in resp.text.lower()


def test_dashboard_references_data_endpoints(client: TestClient) -> None:
    body = client.get("/dashboard").text
    # The page polls the existing JSON APIs client-side.
    assert "/tasks/" in body
    assert "/health" in body


def test_dashboard_has_no_baked_secret(client: TestClient) -> None:
    body = client.get("/dashboard").text
    # Token is entered by the user and kept in localStorage, never embedded.
    assert "localStorage" in body
    # The auth header is built from getToken() at runtime, not a baked value.
    assert 'Bearer " + getToken()' in body
