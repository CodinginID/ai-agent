"""Port untuk text → embedding vector.

Dua mode:
- ``embed(text)`` — single text, untuk query recall.
- ``embed_batch(texts)`` — list of texts, untuk bulk indexing.

Implementor:
- ``FastEmbedAdapter`` — local CPU, default ``all-MiniLM-L6-v2`` (384-dim).
  Cocok untuk VPS minimal (~90 MB model, ~15 ms per call CPU).
- ``OllamaEmbedder`` — pakai Ollama HTTP, default ``nomic-embed-text``
  (768-dim). Pilih ini kalau backend sudah jalan Ollama.

Embedding wajib L2-normalized supaya cosine similarity bekerja benar di
``KnowledgeStore`` adapter pgvector. FastEmbed normalize by default; Ollama
biasanya tidak — adapter harus normalisasi.
"""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    @property
    def dimension(self) -> int:
        """Embedding dim — harus cocok dengan ``KnowledgeChunkModel.embedding``."""
        ...

    def embed(self, text: str) -> list[float]:
        """Embed satu text — return L2-normalized vector."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed list of texts. Lebih efisien dibanding loop ``embed`` per item."""
        ...
