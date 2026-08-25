"""GLM (Zhipu) adapter — cloud LLM via API OpenAI-compatible. Implement ``AIProvider``.

Berbeda dari ``glm_bin`` (delegate CLI di config): ini provider 'otak'
orchestrator lewat HTTP API ``{base_url}/chat/completions`` dengan ``GLM_API_KEY``.

Retry policy (internal): 3x retries, 1s / 2s / 4s backoff + jitter.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
import json
import logging

import httpx

from app.domain.exceptions import AIProviderError
from app.safety.redact import redact_secrets

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "glm-4-plus"
_DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


@dataclass
class GLMAdapter:
    api_key: str = field(repr=False)
    model: str = _DEFAULT_MODEL
    base_url: str = _DEFAULT_BASE_URL
    max_tokens: int = 16000
    timeout: int = 120

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _payload(self, prompt: str, stream: bool) -> dict[str, object]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "stream": stream,
            "messages": [{"role": "user", "content": prompt}],
        }

    def chat(self, prompt: str) -> str:
        from app.adapters.retry import retry_with_backoff

        def _impl() -> str:
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(prompt, stream=False),
                    timeout=self.timeout,
                )
                resp.raise_for_status()
            except Exception as exc:
                log.warning("glm chat gagal: model=%s error=%s", self.model, redact_secrets(str(exc)))
                raise AIProviderError(f"GLM request failed: {exc}") from exc
            data = resp.json()
            try:
                return (data["choices"][0]["message"]["content"] or "").strip()
            except (KeyError, IndexError, TypeError) as exc:
                raise AIProviderError(f"GLM response tidak terduga: {data}") from exc

        return retry_with_backoff(_impl, max_retries=3, base_delay=1.0, max_delay=4.0, jitter=True)()

    def chat_stream(self, prompt: str) -> Iterator[str]:
        from app.adapters.retry import retry_with_backoff

        def _impl() -> Iterator[str]:
            try:
                with httpx.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(prompt, stream=True),
                    timeout=self.timeout,
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                        if delta:
                            yield delta
            except AIProviderError:
                raise
            except Exception as exc:
                log.warning("glm stream gagal: model=%s error=%s", self.model, redact_secrets(str(exc)))
                raise AIProviderError(f"GLM stream failed: {exc}") from exc

        yield from retry_with_backoff(_impl, max_retries=3, base_delay=1.0, max_delay=4.0, jitter=True)()
