"""Ollama-backed Embedder adapter.

Pakai HTTP API ``/api/embeddings`` di Ollama. Default model
``nomic-embed-text`` (768-dim, ~140 MB Q4). Pilih ini kalau backend sudah
jalan Ollama untuk LLM chat — gratis ekstra, share infra.

Ollama tidak L2-normalize output by default, jadi adapter normalize
manual supaya cosine similarity bekerja konsisten dengan FastEmbed adapter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import requests  # type: ignore[import-untyped]

from app.domain.exceptions import AIProviderError

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_DIMENSION = 768


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


@dataclass
class OllamaEmbedder:
    url: str
    model: str = DEFAULT_MODEL
    dim: int = DEFAULT_DIMENSION
    timeout: int = 60

    @property
    def dimension(self) -> int:
        return self.dim

    def embed(self, text: str) -> list[float]:
        try:
            resp = requests.post(
                f"{self.url.rstrip('/')}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise AIProviderError(f"Ollama embed failed: {exc}") from exc

        raw = payload.get("embedding")
        if not isinstance(raw, list) or not raw:
            raise AIProviderError(f"Ollama embed returned no vector: {payload}")
        return _l2_normalize([float(x) for x in raw])

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama HTTP belum support batch /api/embeddings — jalan per-item.
        # Tidak ideal untuk index banyak chunk; pertimbangkan FastEmbed untuk
        # bulk indexing.
        return [self.embed(t) for t in texts]
