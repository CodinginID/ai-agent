"""Port untuk per-user rate limiter.

Domain pakai ini untuk gate request masuk ke pipeline orchestrator
sebelum kena AI provider (Ollama) yang resource-bound.
"""

from __future__ import annotations

from typing import Protocol


class RateLimiterPort(Protocol):
    def is_allowed(self, user_id: str) -> bool: ...
