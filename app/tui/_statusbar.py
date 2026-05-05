"""Status bar text + background health probe."""

from __future__ import annotations

import asyncio

import httpx
from prompt_toolkit.formatted_text import FormattedText

from app.config import settings
from app.tui import _state
from app.tui._http import client, fmt_http_error


def get_status_bar_text() -> FormattedText:
    online = _state.status.get("online", "?")
    mode = _state.status.get("mode", "-")
    users = _state.status.get("users", "?")

    if _state.active_session is not None:
        user_label = (
            _state.active_session.email
            or _state.active_session.user_id[:8]
        )
        user_part = ("class:status.user", f"as: {user_label}")
    else:
        user_part = ("class:status.warn", "not logged in — /login")

    if online == "yes":
        indicator: list[tuple[str, str]] = [("class:status.ok", " ● online")]
    elif online == "?":
        indicator = [("class:status.dim", " ◌ connecting…")]
    else:
        indicator = [("class:status.err", " ● offline")]

    return FormattedText([
        *indicator,
        ("class:status.sep", "  │  "),
        ("class:status.dim", f"mode: {mode}"),
        ("class:status.sep", "  │  "),
        ("class:status.dim", f"users: {users}"),
        ("class:status.sep", "  │  "),
        user_part,
        ("class:status.sep", "  │  "),
        ("class:status.dim", settings.app_url),
        ("class:status.dim", " "),
    ])


async def probe_health() -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as c:
            r = await c.get(f"{settings.app_url}/health")
        if r.status_code == 200:
            return True, str(r.json().get("mode", "unknown"))
        return False, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, fmt_http_error(exc)


async def update_status() -> None:
    reachable, mode = await probe_health()
    if reachable:
        _state.status["online"] = "yes"
        _state.status["mode"] = mode
        try:
            async with client() as c:
                r = await c.get("/admin/status")
            if r.status_code == 200:
                data = r.json()
                _state.status["users"] = str(data.get("user_count", "?"))
        except httpx.HTTPError:
            pass
    else:
        _state.status["online"] = "no"
    if _state.app is not None:
        _state.app.invalidate()


async def status_loop() -> None:
    while _state.running[0]:
        await update_status()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return
