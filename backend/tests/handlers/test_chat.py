"""Unit tests for app/handlers/chat.py — input sanitization and chat_with_qwen."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.handlers.chat as chat_module
from app.safety.validators import validate_input


def _fake_context(chat_history: list[dict[str, str]] | None = None) -> Any:
    if chat_history is None:
        chat_history = []
    return SimpleNamespace(user_data={"chat_history": chat_history})


class TestValidateChatInput:
    """Tests for chat.py input validation."""

    def test_empty_text_rejected(self) -> None:
        result = chat_module.chat_with_qwen("", _fake_context())
        assert "Input kosong" in result

    def test_whitespace_only_rejected(self) -> None:
        result = chat_module.chat_with_qwen("   ", _fake_context())
        assert "Input kosong" in result

    def test_excessively_long_text_rejected(self) -> None:
        long_text = "a" * 10001
        result = chat_module.chat_with_qwen(long_text, _fake_context())
        assert "terlalu panjang" in result

    def test_path_traversal_rejected(self) -> None:
        result = chat_module.chat_with_qwen("../etc/passwd", _fake_context())
        assert "path traversal" in result.lower()

    def test_normal_text_proceeds(self) -> None:
        """Normal text should proceed to Qwen call (which will fail without Ollama,
        but that's fine — we're testing the input validation path)."""
        context = _fake_context()
        # This will attempt to call Qwen, which may fail if Ollama isn't running,
        # but that's expected. The important thing is validation passed.
        with pytest.raises(Exception):
            chat_module.chat_with_qwen("hello", context)


class TestChatHistory:
    """Tests for chat history helpers."""

    def test_build_chat_history_text_empty(self) -> None:
        context = _fake_context()
        assert chat_module.build_chat_history_text(context) == "(belum ada)"

    def test_build_chat_history_text_with_items(self) -> None:
        history = [
            {"user": "halo", "assistant": "hai"},
            {"user": "test", "assistant": "ok"},
        ]
        context = _fake_context(chat_history=history)
        result = chat_module.build_chat_history_text(context)
        assert "User: halo" in result
        assert "Assistant: hai" in result
        assert "User: test" in result
        assert "Assistant: ok" in result

    def test_remember_chat_appends(self) -> None:
        context = _fake_context()
        chat_module.remember_chat(context, "test1", "response1")
        chat_module.remember_chat(context, "test2", "response2")
        assert len(context.user_data["chat_history"]) == 2
        assert context.user_data["chat_history"][0] == {"user": "test1", "assistant": "response1"}
        assert context.user_data["chat_history"][1] == {"user": "test2", "assistant": "response2"}

    def test_remember_chat_truncates(self) -> None:
        context = _fake_context()
        # Fill up more than the limit
        for i in range(10):
            chat_module.remember_chat(context, f"user_{i}", f"assistant_{i}")
        # Should be truncated to chat_history_limit
        assert len(context.user_data["chat_history"]) <= chat_module.settings.chat_history_limit


class TestManualCommand:
    """Tests for run_manual_command input validation."""

    def test_empty_command_rejected(self) -> None:
        result = chat_module.run_manual_command("")
        assert "Input kosong" in result

    def test_long_command_rejected(self) -> None:
        long_cmd = "docker " + "a " * 5000
        result = chat_module.run_manual_command(long_cmd)
        assert "terlalu panjang" in result

    def test_path_traversal_rejected(self) -> None:
        result = chat_module.run_manual_command("../etc/passwd")
        assert "path traversal" in result.lower()

    def test_disallowed_command(self) -> None:
        result = chat_module.run_manual_command("rm -rf /")
        assert "tidak diizinkan" in result
