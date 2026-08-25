# app/ports/ai_provider_resolver.py
"""Port untuk resolve AIProvider per-user.

Memungkinkan tiap user memilih provider (Ollama/Claude/dst) untuk otak
orchestrator. Domain hanya kenal abstraksi ini; resolusi konkret di adapter.
"""

from __future__ import annotations

from typing import Protocol

from app.ports.ai_provider import AIProvider


class AIProviderResolver(Protocol):
    def for_user(self, user_id: str) -> AIProvider: ...
