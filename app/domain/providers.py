# app/domain/providers.py
"""Satu sumber kebenaran untuk daftar provider 'otak' (LLM) yang diizinkan.

CLOUD_PROVIDERS butuh API key (BYOK) dan dijalankan di server via
``app.adapters.ai_provider_factory``. CLI_PROVIDERS ("claude-cli"/"glm-cli")
tidak butuh key sama sekali — brain + semua peran dijalankan di worker CLI
milik user sendiri (lihat ``app.adapters.worker_dispatch._PROVIDER_AGENT``).
"""

from __future__ import annotations

CLOUD_PROVIDERS: frozenset[str] = frozenset({"anthropic", "glm"})
CLI_PROVIDERS: frozenset[str] = frozenset({"claude-cli", "glm-cli"})
MOCK_PROVIDER = "mock"

ALL_PROVIDERS: frozenset[str] = CLOUD_PROVIDERS | CLI_PROVIDERS | frozenset({MOCK_PROVIDER})


def is_cli_provider(name: str) -> bool:
    """True kalau ``name`` adalah provider CLI lokal (tanpa key, via worker)."""
    return (name or "").strip().lower() in CLI_PROVIDERS
