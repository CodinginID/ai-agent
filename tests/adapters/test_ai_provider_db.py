# tests/adapters/test_ai_provider_db.py
from __future__ import annotations

from app.adapters.ai_provider_db import DbAIProviderResolver, personal_anthropic_key_var
from app.adapters.anthropic import AnthropicAdapter
from app.adapters.ollama import OllamaAdapter
from app.config import load_settings


class _FakeRepo:
    def __init__(self, mapping: dict[str, tuple[str, str | None]]) -> None:
        self._m = mapping

    def get(self, user_id: str) -> tuple[str, str | None] | None:
        return self._m.get(user_id)


def test_user_with_preference_gets_chosen_provider() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), load_settings()
    )
    assert isinstance(resolver.for_user("u1"), AnthropicAdapter)


def test_user_without_preference_gets_default() -> None:
    resolver = DbAIProviderResolver(_FakeRepo({}), load_settings())
    assert isinstance(resolver.for_user("u1"), OllamaAdapter)


def test_same_provider_model_is_cached() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), load_settings()
    )
    assert resolver.for_user("u1") is resolver.for_user("u1")


def test_personal_key_changes_cache() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), load_settings()
    )

    token = personal_anthropic_key_var.set("key-1")
    p1 = resolver.for_user("u1")
    assert isinstance(p1, AnthropicAdapter)
    assert p1.api_key == "key-1"

    personal_anthropic_key_var.set("key-2")
    p2 = resolver.for_user("u1")
    assert isinstance(p2, AnthropicAdapter)
    assert p2.api_key == "key-2"
    assert p1 is not p2

    personal_anthropic_key_var.reset(token)
