from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.anthropic import AnthropicAdapter
from app.domain.exceptions import AIProviderError


class _FakeMessages:
    def __init__(self, blocks: list[Any] | Exception) -> None:
        self._blocks = blocks

    def create(self, **kwargs: Any) -> Any:
        if isinstance(self._blocks, Exception):
            raise self._blocks
        return SimpleNamespace(content=self._blocks)


def _text_block(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)


def test_chat_joins_text_blocks() -> None:
    adapter = AnthropicAdapter(api_key="k", model="claude-opus-4-8")
    adapter._client = SimpleNamespace(  # type: ignore[attr-defined]
        messages=_FakeMessages([_text_block("hello "), _text_block("world")])
    )
    assert adapter.chat("hi") == "hello world"


def test_chat_wraps_sdk_error_as_domain_error() -> None:
    adapter = AnthropicAdapter(api_key="k")
    adapter._client = SimpleNamespace(  # type: ignore[attr-defined]
        messages=_FakeMessages(RuntimeError("boom"))
    )
    with pytest.raises(AIProviderError):
        adapter.chat("hi")
