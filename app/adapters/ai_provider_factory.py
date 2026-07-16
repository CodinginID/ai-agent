# app/adapters/ai_provider_factory.py
"""Factory: (provider, model) → AIProvider konkret dengan kredensial.

Mendukung key server-side bawaan atau key personal yang di-inject per request.
"""

from __future__ import annotations

from app.adapters.anthropic import AnthropicAdapter
from app.adapters.ollama import OllamaAdapter
from app.config import Settings
from app.ports.ai_provider import AIProvider

_ALIASES = {"claude": "anthropic"}


def build_ai_provider(
    provider: str, model: str | None, settings: Settings, personal_key: str | None = None
) -> AIProvider:
    name = _ALIASES.get(provider.strip().lower(), provider.strip().lower())
    if name == "ollama":
        return OllamaAdapter(
            url=settings.qwen_url,
            model=model or settings.qwen_model,
            timeout=settings.command_timeout * 3,
        )
    if name == "anthropic":
        api_key = personal_key or settings.anthropic_api_key
        return AnthropicAdapter(
            api_key=api_key,
            model=model or settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )
    raise ValueError(f"Unknown AI provider: {provider!r}")
