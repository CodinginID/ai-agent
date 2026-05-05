"""Ollama adapter — implement ``AIProvider`` port.

Mendukung dua mode:

- ``chat(prompt)`` — blocking, return string penuh. Cocok untuk intent
  classifier dan summarizer.
- ``chat_stream(prompt)`` — yield chunk teks token-per-token. Cocok untuk
  TUI / SSE.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

import requests  # type: ignore[import-untyped]


@dataclass
class OllamaAdapter:
    url: str
    model: str
    timeout: int = 60

    def chat(self, prompt: str) -> str:
        resp = requests.post(
            self.url,
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return str(resp.json().get("response", "")).strip()

    def chat_stream(self, prompt: str) -> Iterator[str]:
        with requests.post(
            self.url,
            json={"model": self.model, "prompt": prompt, "stream": True},
            timeout=self.timeout,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError:
                    # Ollama biasanya selalu kirim JSON per line — kalau tidak,
                    # skip diam-diam supaya stream tetap jalan.
                    continue
                chunk = payload.get("response")
                if chunk:
                    yield str(chunk)
                if payload.get("done"):
                    break
