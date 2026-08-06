"""Task-level RAG memory adapter — recall before planning, index after closing.

Reuses the existing RAG building blocks (``Embedder`` + ``KnowledgeStore``) but
operates at task granularity, tagging chunks with ``meta["kind"] == "task_plan"``
so task memory never mixes with the step-output chunks ``worker_ws`` indexes.
Recall filters on that tag.

Best-effort throughout: a missing embedder (RAG disabled) or any backend error
degrades to "no extra context" / "skip index" rather than failing the task.
Scoped to the user's default project, mirroring ``worker_ws`` resolution.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ports.embedder import Embedder
    from app.ports.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)

_KIND = "task_plan"
MAX_EMBED_CHARS = 4000
MAX_RECALL_CONTEXT_CHARS = 1500


def _resolve_project_id(user_id: str) -> str:
    from app.adapters.database.repositories import ControlPlaneRepository
    from app.composition import _session_factory

    with _session_factory()() as session:
        repo = ControlPlaneRepository(session)
        project = repo.get_or_create_default_project(user_id)
        project_id = project.id
        session.commit()
    return project_id


class RagTaskMemory:
    """Concrete TaskMemoryPort backed by Embedder + KnowledgeStore."""

    def __init__(
        self,
        embedder: Embedder | None,
        store: KnowledgeStore,
        recall_k: int = 3,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._k = recall_k

    async def recall_for_planning(
        self, user_id: str, request: str, base_context: str,
    ) -> str:
        if self._embedder is None or not request.strip():
            return base_context
        try:
            project_id = await asyncio.to_thread(_resolve_project_id, user_id)
            q_emb = await asyncio.to_thread(self._embedder.embed, request[:MAX_EMBED_CHARS])
            # Over-fetch then filter to task_plan chunks; recall has no meta filter.
            hits = await self._store.recall(project_id, q_emb, k=self._k * 4)
        except Exception as exc:
            logger.warning("task memory recall failed: %s", exc)
            return base_context

        task_hits = [h for h in hits if h.chunk.meta.get("kind") == _KIND][: self._k]
        if not task_hits:
            return base_context

        lines = ["Task serupa di masa lalu (untuk referensi perencanaan):"]
        total = 0
        for i, hit in enumerate(task_hits, 1):
            text = hit.chunk.text
            if total + len(text) > MAX_RECALL_CONTEXT_CHARS:
                text = text[: MAX_RECALL_CONTEXT_CHARS - total]
                lines.append(f"[{i}] (truncated) {text}…")
                break
            lines.append(f"[{i}] {text}")
            total += len(text)

        recall_block = "\n".join(lines)
        return f"{recall_block}\n\n---\n\n{base_context}" if base_context else recall_block

    async def index_task(
        self, user_id: str, request: str, summary: str, outcome_note: str,
    ) -> None:
        if self._embedder is None:
            return
        text = f"Request: {request}\nRingkasan: {summary}\nHasil: {outcome_note}"[:MAX_EMBED_CHARS]
        try:
            project_id = await asyncio.to_thread(_resolve_project_id, user_id)
            emb = await asyncio.to_thread(self._embedder.embed, text)
            await self._store.index(
                project_id, text, emb,
                meta={"kind": _KIND, "request": request[:200]},
            )
        except Exception as exc:
            logger.warning("task memory index failed: %s", exc)
