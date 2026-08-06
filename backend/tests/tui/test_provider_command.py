"""Unit tests untuk /provider command (TUI) — app/tui/_commands.py.

HTTP call ke backend di-mock lewat ``httpx.AsyncClient`` patch, mengikuti
konvensi tests/adapters/test_github.py.
"""

from __future__ import annotations

import json as _json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.tui._commands as cmds
from app.tui._session import Session


@pytest.fixture(autouse=True)
def _silence_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmds, "println", MagicMock())
    monkeypatch.setattr(cmds, "print_parts", MagicMock())


@pytest.fixture(autouse=True)
def _logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cmds._state,
        "active_session",
        Session(
            token="tok-1",
            user_id="u1",
            email="a@b.com",
            display_name=None,
            backend_url="http://x",
        ),
    )


def _response(status_code: int, data: object) -> httpx.Response:
    return httpx.Response(status_code, content=_json.dumps(data).encode())


def _printed() -> str:
    return " ".join(str(call.args[-1]) for call in cmds.println.call_args_list)


@pytest.mark.asyncio
async def test_no_args_shows_active_provider() -> None:
    resp = _response(
        200, {"provider": "anthropic", "model": "claude-3-opus", "is_default": False}
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
        await cmds.cmd_provider([])

    printed = _printed()
    assert "anthropic" in printed
    assert "claude-3-opus" in printed
    assert "ollama" in printed


@pytest.mark.asyncio
async def test_set_valid_provider_persists_and_confirms() -> None:
    resp = _response(200, {"ok": True})
    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp
    ) as mock_post:
        await cmds.cmd_provider(["anthropic", "claude-3-opus"])

    _, kwargs = mock_post.call_args
    assert kwargs["json"] == {"provider": "anthropic", "model": "claude-3-opus"}
    assert "anthropic" in _printed()


@pytest.mark.asyncio
async def test_set_invalid_provider_replies_friendly_error() -> None:
    resp = _response(400, {"detail": "Unknown AI provider: 'foobar'"})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
        await cmds.cmd_provider(["foobar"])

    assert "unknown ai provider" in _printed().lower()
