"""Async HTTP client factory + helpers ke backend."""

from __future__ import annotations

import httpx

from app.config import settings

HTTP_TIMEOUT_SEC = 5.0
CHAT_TIMEOUT_SEC = 120.0


def client() -> httpx.AsyncClient:
    headers = {"User-Agent": "octopus-tui/0.1.0"}
    if settings.admin_token:
        headers["Authorization"] = f"Bearer {settings.admin_token}"
    return httpx.AsyncClient(
        base_url=settings.app_url,
        timeout=HTTP_TIMEOUT_SEC,
        headers=headers,
        trust_env=False,
    )


def fmt_http_error(exc: httpx.HTTPError) -> str:
    return f"{type(exc).__name__}: {exc}"


async def fetch_emails() -> list[str]:
    try:
        async with client() as c:
            r = await c.get("/admin/users")
        if r.status_code == 200:
            return [
                u.get("email", "")
                for u in r.json().get("users", [])
                if u.get("email")
            ]
    except httpx.HTTPError:
        pass
    return []
