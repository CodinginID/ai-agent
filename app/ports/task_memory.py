"""Port for task-level RAG memory — recall before planning, index after closing.

Distinct from the *step-output* RAG already wired in ``worker_ws`` (which embeds
each worker's output to enrich the next dispatch). This layer remembers whole
**tasks**: before the PM decomposes a request, recall summaries of similar past
tasks and feed them as planning context; after a task closes, index its summary
so future planning benefits.

Keeping it a Protocol means TaskRunner depends on the port, not the embedder /
knowledge-store adapters — tests inject a recording fake or the no-op default.
"""

from __future__ import annotations

from typing import Protocol


class TaskMemoryPort(Protocol):
    async def recall_for_planning(
        self, user_id: str, request: str, base_context: str,
    ) -> str:
        """Return ``base_context`` augmented with similar past-task summaries.

        Must be best-effort: on any failure return ``base_context`` unchanged —
        planning memory is an enhancement, never a critical path.
        """
        ...

    async def index_task(
        self, user_id: str, request: str, summary: str, outcome_note: str,
    ) -> None:
        """Persist a closed task's summary for future planning recall."""
        ...


class NullTaskMemory:
    """No-op task memory — the default so TaskRunner works without wiring."""

    async def recall_for_planning(
        self, user_id: str, request: str, base_context: str,
    ) -> str:
        return base_context

    async def index_task(
        self, user_id: str, request: str, summary: str, outcome_note: str,
    ) -> None:
        return None
