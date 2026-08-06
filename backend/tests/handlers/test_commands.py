"""Unit tests for app/handlers/commands.py — input validation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

import app.handlers.commands as commands_module


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
    monkeypatch.setattr(commands_module, "deny_if_unauthorized", AsyncMock(return_value=False))


class TestToolCmd:
    """Tests for /tool command input validation."""

    @pytest.mark.asyncio
    async def test_empty_tool_input(self) -> None:
        update = _make_update()
        await commands_module.tool_cmd(update, _make_context([]))
        reply = update.message.reply_text.await_args.args[0]
        assert "format" in reply.lower()

    @pytest.mark.asyncio
    async def test_tool_input_too_long(self) -> None:
        long_input = "echo " + "x " * 2500
        update = _make_update()
        await commands_module.tool_cmd(update, _make_context([long_input]))
        reply = update.message.reply_text.await_args.args[0]
        assert "terlalu panjang" in reply.lower()

    @pytest.mark.asyncio
    async def test_tool_path_traversal(self) -> None:
        update = _make_update()
        await commands_module.tool_cmd(update, _make_context(["echo ../etc/passwd"]))
        reply = update.message.reply_text.await_args.args[0]
        assert "path traversal" in reply.lower()


class TestCodexCmd:
    """Tests for /codex command input validation."""

    @pytest.mark.asyncio
    async def test_empty_codex_input(self) -> None:
        update = _make_update()
        await commands_module.codex_cmd(update, _make_context([]))
        reply = update.message.reply_text.await_args.args[0]
        assert "format" in reply.lower()

    @pytest.mark.asyncio
    async def test_codex_input_too_long(self) -> None:
        long_prompt = "test " * 1000
        update = _make_update()
        await commands_module.codex_cmd(update, _make_context([long_prompt]))
        reply = update.message.reply_text.await_args.args[0]
        assert "terlalu panjang" in reply.lower()

    @pytest.mark.asyncio
    async def test_codex_path_traversal(self) -> None:
        update = _make_update()
        await commands_module.codex_cmd(update, _make_context(["../etc/passwd"]))
        reply = update.message.reply_text.await_args.args[0]
        assert "path traversal" in reply.lower()


class TestClaudeCmd:
    """Tests for /claude command input validation."""

    @pytest.mark.asyncio
    async def test_empty_claude_input(self) -> None:
        update = _make_update()
        await commands_module.claude_cmd(update, _make_context([]))
        reply = update.message.reply_text.await_args.args[0]
        assert "format" in reply.lower()

    @pytest.mark.asyncio
    async def test_claude_input_too_long(self) -> None:
        long_prompt = "test " * 1000
        update = _make_update()
        await commands_module.claude_cmd(update, _make_context([long_prompt]))
        reply = update.message.reply_text.await_args.args[0]
        assert "terlalu panjang" in reply.lower()

    @pytest.mark.asyncio
    async def test_claude_path_traversal(self) -> None:
        update = _make_update()
        await commands_module.claude_cmd(update, _make_context(["../etc/passwd"]))
        reply = update.message.reply_text.await_args.args[0]
        assert "path traversal" in reply.lower()


class TestSpfCmd:
    """Tests for /spf command input validation."""

    @pytest.mark.asyncio
    async def test_empty_spf_input(self) -> None:
        update = _make_update()
        await commands_module.spf_cmd(update, _make_context([]))
        reply = update.message.reply_text.await_args.args[0]
        assert "format" in reply.lower()

    @pytest.mark.asyncio
    async def test_spf_path_traversal(self) -> None:
        update = _make_update()
        await commands_module.spf_cmd(update, _make_context(["../etc/passwd"]))
        reply = update.message.reply_text.await_args.args[0]
        assert "path traversal" in reply.lower()
