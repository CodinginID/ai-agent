"""Ollama adapter — implement ``AIProvider`` port.

Mendukung dua mode:

- ``chat(prompt)`` — blocking, return string penuh. Cocok untuk intent
  classifier dan summarizer.
- ``chat_stream(prompt)`` — yield chunk teks token-per-token. Cocok untuk
  TUI / SSE.

Retry policy (internal): 3x retries, 1s / 2s / 4s backoff + jitter.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass

import requests  # type: ignore[import-untyped]

from app.domain.exceptions import AIProviderError
from app.safety.redact import redact_secrets

log = logging.getLogger(__name__)


def _ollama_chat(url: str, model: str, prompt: str, timeout: int) -> str:
    log.debug("ollama chat: url=%s model=%s timeout=%ds", redact_secrets(url), model, timeout)
    try:
        resp = requests.post(
            url,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        return str(resp.json().get("response", "")).strip()
    except requests.RequestException as exc:
        log.warning("ollama request failed: url=%s error=%s", redact_secrets(url), exc)
        raise AIProviderError(f"Ollama request failed: {exc}") from exc


def _ollama_chat_stream(url: str, model: str, prompt: str, timeout: int) -> Iterator[str]:
    try:
        with requests.post(
            url,
            json={"model": model, "prompt": prompt, "stream": True},
            timeout=timeout,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                chunk = payload.get("response")
                if chunk:
                    yield str(chunk)
                if payload.get("done"):
                    break
    except requests.RequestException as exc:
        raise AIProviderError(f"Ollama stream failed: {exc}") from exc


@dataclass
class OllamaAdapter:
    url: str
    model: str
    timeout: int = 60

    def chat(self, prompt: str) -> str:
        from app.adapters.retry import retry_with_backoff

        return retry_with_backoff(
            _ollama_chat,
            max_retries=3,
            base_delay=1.0,
            max_delay=4.0,
            jitter=True,
        )(self.url, self.model, prompt, self.timeout)

    def chat_stream(self, prompt: str) -> Iterator[str]:
        from app.adapters.retry import retry_with_backoff

        yield from retry_with_backoff(
            _ollama_chat_stream,
            max_retries=3,
            base_delay=1.0,
            max_delay=4.0,
            jitter=True,
        )(self.url, self.model, prompt, self.timeout)
