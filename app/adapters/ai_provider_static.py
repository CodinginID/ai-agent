# app/adapters/ai_provider_static.py
"""Resolver yang selalu mengembalikan satu provider — mempertahankan perilaku
single-provider (dipakai test & saat DB preferensi tidak di-wire)."""

from __future__ import annotations

from dataclasses import dataclass

from app.ports.ai_provider import AIProvider


@dataclass(frozen=True)
class StaticAIProviderResolver:
    provider: AIProvider

    def for_user(self, user_id: str) -> AIProvider:
        return self.provider
