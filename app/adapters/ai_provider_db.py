# app/adapters/ai_provider_db.py
"""Resolver per-user berbasis DB — baca preferensi, bangun provider, cache."""

from __future__ import annotations

import contextvars
from typing import Protocol

from app.adapters.ai_provider_factory import build_ai_provider
from app.config import Settings
from app.domain.exceptions import AIProviderError
from app.domain.providers import is_cli_provider
from app.ports.ai_provider import AIProvider

personal_anthropic_key_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "personal_anthropic_key", default=None
)


class _PrefReader(Protocol):
    def get(self, user_id: str) -> tuple[str, str | None] | None: ...


class DbAIProviderResolver:
    def __init__(
        self, repo: _PrefReader, settings: Settings, *, degrade_cli_to_mock: bool = False
    ) -> None:
        self._repo = repo
        self._settings = settings
        # Chat brain saja: provider CLI lokal (claude-cli/glm-cli) tidak punya
        # adapter cloud (build_ai_provider raise) — kerja berat sudah
        # didelegasikan ke worker lewat dispatch override, jadi brain di sini
        # cukup degrade ke MockAIProvider (bukan lempar error tiap chat).
        # TaskRunner/ExecutionLoop TIDAK memakai flag ini — mereka butuh raise
        # supaya jatuh ke jalur decompose-via-worker.
        self._degrade_cli_to_mock = degrade_cli_to_mock
        # Hanya key server-side (personal_key None) yang layak di-cache untuk
        # lifetime process — personal key per-user tidak boleh menumpuk di
        # cache global (bocor plaintext secret + tumbuh tak terbatas).
        self._cache: dict[tuple[str, str | None], AIProvider] = {}

    def for_user(self, user_id: str) -> AIProvider:
        pref = self._repo.get(user_id)
        provider, model = pref if pref else (self._settings.ai_provider_default, None)
        personal_key = personal_anthropic_key_var.get()

        try:
            if personal_key is not None:
                return build_ai_provider(provider, model, self._settings, personal_key=personal_key)

            key = (provider, model)
            cached = self._cache.get(key)
            if cached is None:
                cached = build_ai_provider(provider, model, self._settings, personal_key=None)
                self._cache[key] = cached
            return cached
        except AIProviderError:
            if self._degrade_cli_to_mock and is_cli_provider(provider):
                from app.adapters.mock_llm import MockAIProvider
                return MockAIProvider()
            raise
