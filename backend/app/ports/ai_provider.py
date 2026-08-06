"""Port untuk AI provider (Ollama, OpenAI, Anthropic, dst).

Dua method:
- ``chat`` — blocking, return string penuh.
- ``chat_stream`` — yield chunk teks token-by-token.

Domain layer cuma kenal abstraksi ini; implementasi konkret ada di
``app/adapters/ollama.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol


class AIProvider(Protocol):
    def chat(self, prompt: str) -> str: ...

    def chat_stream(self, prompt: str) -> Iterator[str]: ...
