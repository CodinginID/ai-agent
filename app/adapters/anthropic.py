"""Anthropic (Claude) adapter — implement ``AIProvider`` port via SDK resmi.

``chat`` blocking (gabung text blocks); ``chat_stream`` streaming token.
Parameter thinking sengaja diomit — Opus 4.8 jalan tanpa thinking, paling
cepat/murah untuk intent classify, chat, dan summarize.

Retry policy (internal): 3x retries, 1s / 2s / 4s backoff + jitter.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

import anthropic

from app.domain.exceptions import AIProviderError
from app.safety.redact import redact_secrets

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class AnthropicAdapter:
    api_key: str = field(repr=False)
    model: str = _DEFAULT_MODEL
    max_tokens: int = 16000
    _client: anthropic.Anthropic = field(init=False, repr=False)

    def __post_init__(self) -> None:
        log.debug("instantiate AnthropicAdapter: model=%s api_key=%s", self.model, redact_secrets(self.api_key))
        self._client = anthropic.Anthropic(api_key=self.api_key)

    def chat(self, prompt: str) -> str:
        from app.adapters.retry import retry_with_backoff

        def _chat_impl() -> str:
            try:
                resp = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
            except Exception as exc:  # SDK exceptions + koneksi
                log.warning("anthropic chat gagal: model=%s error=%s", self.model, redact_secrets(str(exc)))
                raise AIProviderError(f"Anthropic request failed: {exc}") from exc
            return "".join(
                getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
            ).strip()

        return retry_with_backoff(
            _chat_impl,
            max_retries=3,
            base_delay=1.0,
            max_delay=4.0,
            jitter=True,
        )()

    def chat_stream(self, prompt: str) -> Iterator[str]:
        from app.adapters.retry import retry_with_backoff

        def _stream_impl() -> Iterator[str]:
            try:
                with self._client.messages.stream(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    yield from stream.text_stream
            except Exception as exc:
                log.warning("anthropic stream gagal: model=%s error=%s", self.model, redact_secrets(str(exc)))
                raise AIProviderError(f"Anthropic stream failed: {exc}") from exc

        yield from retry_with_backoff(
            _stream_impl,
            max_retries=3,
            base_delay=1.0,
            max_delay=4.0,
            jitter=True,
        )()
