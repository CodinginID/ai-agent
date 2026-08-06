"""Unit tests untuk /provider command (Telegram) — app/handlers/commands.py.

Mirrors gaya test untuk handler lain di repo ini: mock Update/Context via
SimpleNamespace/AsyncMock, tanpa hit Telegram atau DB nyata.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

import app.handlers.auth as auth_module
import app.handlers.commands as commands


class _FakeRepo:
    """Fake UserProviderConfigRepository — no DB, records calls."""

    def __init__(self, pref: tuple[str, str | None] | None = None) -> None:
        self._pref = pref
        self.set_calls: list[tuple[str, str, str | None]] = []

    def get(self, user_id: str) -> tuple[str, str | None] | None:
        return self._pref

    def set(self, user_id: str, provider: str, model: str | None = None) -> None:
        self.set_calls.append((user_id, provider, model))
        self._pref = (provider, model)


def _make_update() -> Any:
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        message=message,
    )


def _make_context(args: list[str]) -> Any:
    return SimpleNamespace(args=args)


@pytest.fixture(autouse=True)
def _authorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(commands, "deny_if_unauthorized", AsyncMock(return_value=False))
    monkeypatch.setattr(auth_module, "resolve_user_id_from_telegram", lambda tg_id: "user-1")
    monkeypatch.setattr(commands, "get_db_session_factory", lambda: object())


def _patch_repo(monkeypatch: pytest.MonkeyPatch, repo: _FakeRepo) -> None:
    import app.adapters.user_provider_config as upc_module

    monkeypatch.setattr(upc_module, "UserProviderConfigRepository", lambda factory: repo)


@pytest.mark.asyncio
async def test_no_args_shows_active_provider_and_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeRepo(pref=("anthropic", "claude-3-opus"))
    _patch_repo(monkeypatch, repo)

    update = _make_update()
    await commands.provider_cmd(update, _make_context([]))

    reply = update.message.reply_text.await_args.args[0]
    assert "anthropic" in reply
    assert "claude-3-opus" in reply
    assert "ollama" in reply


@pytest.mark.asyncio
async def test_set_valid_provider_persists_and_confirms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeRepo(pref=None)
    _patch_repo(monkeypatch, repo)

    update = _make_update()
    await commands.provider_cmd(update, _make_context(["anthropic", "claude-3-opus"]))

    assert repo.set_calls == [("user-1", "anthropic", "claude-3-opus")]
    reply = update.message.reply_text.await_args.args[0]
    assert "anthropic" in reply


@pytest.mark.asyncio
async def test_set_invalid_provider_replies_friendly_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeRepo(pref=None)
    _patch_repo(monkeypatch, repo)

    update = _make_update()
    await commands.provider_cmd(update, _make_context(["foobar"]))

    assert repo.set_calls == []
    reply = update.message.reply_text.await_args.args[0]
    assert "tidak dikenal" in reply.lower()
