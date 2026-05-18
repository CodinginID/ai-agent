"""In-memory KnowledgeStore — untuk unit test dan dev fallback tanpa Postgres."""

from __future__ import annotations

import math
import uuid
from typing import Any

from app.ports.knowledge_store import KnowledgeChunk, RecallResult


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity ∈ [-1, 1]. Return 0.0 untuk vektor nol."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryKnowledgeStore:
    """KnowledgeStore implementation backed by a simple dict.

    Tidak persistent, tidak ANN-indexed — cocok untuk test dan single-process
    dev. Production wajib pakai ``PgVectorKnowledgeStore``.
    """

    def __init__(self) -> None:
        self._chunks: dict[str, tuple[KnowledgeChunk, list[float]]] = {}

    async def index(
        self,
        project_id: str,
        text: str,
        embedding: list[float],
        meta: dict[str, Any] | None = None,
    ) -> str:
        chunk_id = str(uuid.uuid4())
        chunk = KnowledgeChunk(
            id=chunk_id,
            project_id=project_id,
            text=text,
            meta=dict(meta or {}),
        )
        self._chunks[chunk_id] = (chunk, list(embedding))
        return chunk_id

    async def recall(
        self,
        project_id: str,
        query_embedding: list[float],
        k: int = 5,
    ) -> list[RecallResult]:
        scored = [
            RecallResult(chunk=chunk, score=_cosine_similarity(query_embedding, emb))
            for chunk, emb in self._chunks.values()
            if chunk.project_id == project_id
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]

    async def delete_project(self, project_id: str) -> int:
        before = len(self._chunks)
        self._chunks = {
            cid: pair
            for cid, pair in self._chunks.items()
            if pair[0].project_id != project_id
        }
        return before - len(self._chunks)
