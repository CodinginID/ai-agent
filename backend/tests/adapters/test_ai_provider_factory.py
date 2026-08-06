# tests/adapters/test_ai_provider_factory.py
from __future__ import annotations

import pytest

from app.adapters.ai_provider_factory import build_ai_provider
from app.adapters.anthropic import AnthropicAdapter
from app.adapters.ollama import OllamaAdapter
from app.config import load_settings


def test_ollama_provider_returns_ollama_adapter() -> None:
    provider = build_ai_provider("ollama", None, load_settings())
    assert isinstance(provider, OllamaAdapter)


def test_claude_alias_maps_to_anthropic_adapter() -> None:
    provider = build_ai_provider("claude", "claude-opus-4-8", load_settings())
    assert isinstance(provider, AnthropicAdapter)
    assert provider.model == "claude-opus-4-8"


def test_model_none_uses_provider_default() -> None:
    provider = build_ai_provider("anthropic", None, load_settings())
    assert isinstance(provider, AnthropicAdapter)
    assert provider.model == "claude-opus-4-8"


def test_personal_key_overrides_settings() -> None:
    provider = build_ai_provider("anthropic", None, load_settings(), personal_key="pk-123")
    assert isinstance(provider, AnthropicAdapter)
    assert provider.api_key == "pk-123"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        build_ai_provider("gpt", None, load_settings())
