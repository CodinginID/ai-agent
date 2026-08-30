# app/adapters/ai_provider_factory.py
"""Factory: (provider, model) → AIProvider konkret dengan kredensial.

Mendukung key server-side bawaan atau key personal yang di-inject per request.

Setiap adapter yang dikembalikan sudah dibungkus ``CircuitBreaker`` sehingga
cascade failure ke provider eksternal (Ollama/Anthropic) tidak menjatuhkan bot.
"""

from __future__ import annotations

from app.adapters.anthropic import AnthropicAdapter
from app.adapters.circuit_breaker import CircuitBreaker
from app.adapters.glm import GLMAdapter
from app.config import Settings
from app.domain.exceptions import AIProviderError
from app.domain.providers import is_cli_provider
from app.ports.ai_provider import AIProvider

_ALIASES = {"claude": "anthropic", "zhipu": "glm"}

# Default circuit-breaker settings per provider.
_CB_DEFAULTS: dict[str, dict[str, int]] = {
    "anthropic": {"threshold": 3, "timeout": 60},
    "glm": {"threshold": 3, "timeout": 60},
}


def build_ai_provider(
    provider: str, model: str | None, settings: Settings, personal_key: str | None = None
) -> AIProvider:
    name = _ALIASES.get(provider.strip().lower(), provider.strip().lower())
    if is_cli_provider(name):
        # CLI lokal (claude-cli/glm-cli): tidak ada adapter cloud untuk ini —
        # brain + peran dijalankan di worker CLI user (lihat worker_dispatch).
        raise AIProviderError(
            "provider CLI lokal — dijalankan lewat worker, bukan cloud"
        )
    if name == "anthropic":
        api_key = personal_key or settings.anthropic_api_key
        if not api_key:
            raise AIProviderError(
                "Anthropic API key belum diatur — pilih provider & masukkan key kamu dulu (BYOK)."
            )
        raw: AIProvider = AnthropicAdapter(
            api_key=api_key,
            model=model or settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )
    elif name == "glm":
        api_key = personal_key or settings.glm_api_key
        if not api_key:
            raise AIProviderError(
                "GLM API key belum diatur — pilih provider & masukkan key kamu dulu (BYOK)."
            )
        raw = GLMAdapter(
            api_key=api_key,
            model=model or settings.glm_api_model,
            base_url=settings.glm_api_base_url,
            max_tokens=settings.anthropic_max_tokens,
        )
    elif name == "mock":
        # Mode dev/testing tanpa key — respons deterministik.
        from app.adapters.mock_llm import MockAIProvider
        raw = MockAIProvider()
    else:
        raise ValueError(f"Unknown AI provider: {provider!r}")

    cb_cfg = _CB_DEFAULTS.get(name, {"threshold": 3, "timeout": 60})
    breaker = CircuitBreaker(name=f"{name}.{model or 'default'}", **cb_cfg)
    return breaker.wrap_provider(raw)
