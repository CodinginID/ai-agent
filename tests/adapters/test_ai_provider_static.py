# tests/adapters/test_ai_provider_static.py
from __future__ import annotations

from collections.abc import Iterator

from app.adapters.ai_provider_static import StaticAIProviderResolver


class _FakeProvider:
    def chat(self, prompt: str) -> str:
        return "ok"

    def chat_stream(self, prompt: str) -> Iterator[str]:
        yield "ok"


def test_for_user_returns_the_same_provider_for_any_user() -> None:
    provider = _FakeProvider()
    resolver = StaticAIProviderResolver(provider)
    assert resolver.for_user("user-1") is provider
    assert resolver.for_user("user-2") is provider
