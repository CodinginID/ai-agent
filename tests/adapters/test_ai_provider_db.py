# tests/adapters/test_ai_provider_db.py
from __future__ import annotations

import dataclasses

from app.adapters.ai_provider_db import DbAIProviderResolver, personal_anthropic_key_var
from app.adapters.anthropic import AnthropicAdapter
from app.adapters.circuit_breaker import _CircuitBreakerProvider
from app.config import load_settings


class _FakeRepo:
    def __init__(self, mapping: dict[str, tuple[str, str | None]]) -> None:
        self._m = mapping

    def get(self, user_id: str) -> tuple[str, str | None] | None:
        return self._m.get(user_id)


def _settings_with_key() -> object:
    # BYOK: butuh key server-side supaya jalur non-personal bisa build provider.
    return dataclasses.replace(load_settings(), anthropic_api_key="server-key")


def _inner(provider: object) -> object:
    assert isinstance(provider, _CircuitBreakerProvider)
    return provider._inner


def test_user_with_preference_gets_chosen_provider() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), _settings_with_key()
    )
    assert isinstance(_inner(resolver.for_user("u1")), AnthropicAdapter)


def test_user_without_preference_gets_default() -> None:
    resolver = DbAIProviderResolver(_FakeRepo({}), _settings_with_key())
    assert isinstance(_inner(resolver.for_user("u1")), AnthropicAdapter)


def test_same_provider_model_is_cached() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), _settings_with_key()
    )
    assert resolver.for_user("u1") is resolver.for_user("u1")


def test_personal_key_changes_cache() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), _settings_with_key()
    )

    token = personal_anthropic_key_var.set("key-1")
    try:
        p1 = resolver.for_user("u1")
        assert _inner(p1).api_key == "key-1"

        personal_anthropic_key_var.set("key-2")
        p2 = resolver.for_user("u1")
        assert _inner(p2).api_key == "key-2"
        assert p1 is not p2
    finally:
        personal_anthropic_key_var.reset(token)


def test_personal_key_provider_is_not_cached() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), _settings_with_key()
    )

    token = personal_anthropic_key_var.set("key-1")
    try:
        p1 = resolver.for_user("u1")
        assert _inner(p1).api_key == "key-1"
        assert resolver._cache == {}

        p2 = resolver.for_user("u1")
        assert p1 is not p2
        assert resolver._cache == {}
    finally:
        personal_anthropic_key_var.reset(token)


def test_server_key_provider_is_still_cached() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), _settings_with_key()
    )

    p1 = resolver.for_user("u1")
    p2 = resolver.for_user("u1")

    assert p1 is p2
    assert resolver._cache == {("anthropic", "claude-opus-4-8"): p1}
