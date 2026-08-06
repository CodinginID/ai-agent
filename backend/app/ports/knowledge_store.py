"""Port untuk RAG knowledge store — project-scoped semantic memory.

Tugas store:
- ``index`` — simpan satu chunk text + embedding-nya untuk project.
- ``recall`` — top-K chunk paling similar dengan query embedding.

Adapter konkret:
- ``PgVectorKnowledgeStore`` (production) — pakai pgvector cosine distance.
- ``InMemoryKnowledgeStore`` (test/dev) — pure Python cosine.

Embedding di-passing sudah dalam bentuk ``list[float]``; embedder terpisah
(``app.ports.embedder``) yang bertanggung-jawab konversi text → vector.
Pemisahan ini supaya store bisa di-test tanpa model NLP, dan embedder
bisa di-swap (Ollama / fastembed / managed API).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class KnowledgeChunk:
    """Satu fragmen teks dalam project knowledge store."""

    id: str
    project_id: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallResult:
    """Hasil recall — chunk plus similarity score (1.0 = identik, 0.0 = orthogonal)."""

    chunk: KnowledgeChunk
    score: float


class KnowledgeStore(Protocol):
    """Project-scoped vector store. Implementor handle persistence + ANN."""

    async def index(
        self,
        project_id: str,
        text: str,
        embedding: list[float],
        meta: dict[str, Any] | None = None,
    ) -> str:
        """Simpan chunk. Return ID chunk yang baru disimpan."""
        ...

    async def recall(
        self,
        project_id: str,
        query_embedding: list[float],
        k: int = 5,
    ) -> list[RecallResult]:
        """Top-K chunk dengan similarity tertinggi untuk project tersebut."""
        ...

    async def delete_project(self, project_id: str) -> int:
        """Hapus semua chunk milik project. Return jumlah row terhapus."""
        ...
