# tests/adapters/test_ai_provider_factory.py
from __future__ import annotations

import pytest

from app.adapters.ai_provider_factory import build_ai_provider
from app.adapters.anthropic import AnthropicAdapter
from app.adapters.circuit_breaker import _CircuitBreakerProvider
from app.adapters.glm import GLMAdapter
from app.config import load_settings
from app.domain.exceptions import AIProviderError


def _inner(provider: object) -> object:
    """Factory membungkus tiap provider dengan CircuitBreaker — ambil adapter dalamnya."""
    assert isinstance(provider, _CircuitBreakerProvider)
    return provider._inner


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        build_ai_provider("gpt", None, load_settings(), personal_key="pk-1")


def test_missing_key_raises_byok() -> None:
    # Tanpa personal_key & tanpa env key → BYOK: wajib set dulu.
    with pytest.raises(AIProviderError):
        build_ai_provider("anthropic", None, load_settings())


def test_claude_alias_maps_to_anthropic_adapter() -> None:
    provider = build_ai_provider("claude", "claude-opus-4-8", load_settings(), personal_key="pk-1")
    inner = _inner(provider)
    assert isinstance(inner, AnthropicAdapter)
    assert inner.model == "claude-opus-4-8"


def test_model_none_uses_provider_default() -> None:
    provider = build_ai_provider("anthropic", None, load_settings(), personal_key="pk-1")
    inner = _inner(provider)
    assert isinstance(inner, AnthropicAdapter)
    assert inner.model == "claude-opus-4-8"


def test_personal_key_overrides_settings() -> None:
    provider = build_ai_provider("anthropic", None, load_settings(), personal_key="pk-123")
    assert _inner(provider).api_key == "pk-123"


def test_glm_alias_and_adapter() -> None:
    provider = build_ai_provider("zhipu", None, load_settings(), personal_key="pk-1")
    assert isinstance(_inner(provider), GLMAdapter)
