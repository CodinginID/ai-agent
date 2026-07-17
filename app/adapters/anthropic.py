"""Anthropic (Claude) adapter — implement ``AIProvider`` port via SDK resmi.

``chat`` blocking (gabung text blocks); ``chat_stream`` streaming token.
Parameter thinking sengaja diomit — Opus 4.8 jalan tanpa thinking, paling
cepat/murah untuk intent classify, chat, dan summarize.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import anthropic

from app.domain.exceptions import AIProviderError

_DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class AnthropicAdapter:
    api_key: str = field(repr=False)
    model: str = _DEFAULT_MODEL
    max_tokens: int = 16000
    _client: anthropic.Anthropic = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=self.api_key)

    def chat(self, prompt: str) -> str:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # SDK exceptions + koneksi
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc
        return "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()

    def chat_stream(self, prompt: str) -> Iterator[str]:
        try:
            with self._client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                yield from stream.text_stream
        except Exception as exc:
            raise AIProviderError(f"Anthropic stream failed: {exc}") from exc
