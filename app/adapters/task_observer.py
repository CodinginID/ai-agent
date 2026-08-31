"""Task observability adapter — structured stdout log + Redis events stream (PR-5).

Two best-effort sinks, mirroring the audit adapter's split:

1. **stdout** via the stdlib logger — every event becomes a one-line
   ``[ROLE][TASK_ID][STATUS] message`` record. Captured by ``docker logs -f`` /
   ``docker service logs`` so the user can follow a task live with no extra infra.
2. **Redis stream** (``task:events``, capped) — structured rows the ``GET /tasks``
   board reads back to show recent tasks and their last status without SSH.

Implements ``app.ports.task_events.TaskObserver``. Methods are sync and never
raise — observability must not break task execution.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast

from app.adapters.redis_client import get_sync_client, k_task_events

logger = logging.getLogger("octopus.tasks")

_MAX_EVENTS = 5000


def _emit(task_id: str, role: str, status: str, message: str, **extra: str) -> None:
    """Log to stdout and append to the Redis events stream. Best-effort."""
    logger.info("[%s][%s][%s] %s", role, task_id, status, message)
    try:
        client = get_sync_client()
        fields = {
            "ts": datetime.now(UTC).isoformat(),
            "task_id": task_id,
            "role": role,
            "status": status,
            "message": message[:500],
            **extra,
        }
        client.xadd(
            k_task_events(),
            cast("dict[Any, Any]", fields),
            maxlen=_MAX_EVENTS,
            approximate=True,
        )
    except Exception as exc:  # Redis hiccup must not break the task.
        logger.warning("task event stream append failed: %s", exc)


class LoggingTaskObserver:
    """Concrete TaskObserver — structured stdout + Redis events stream."""

    def task_started(self, task_id: str, user_id: str, request: str) -> None:
        _emit(task_id, "pm", "started", request[:120], user_id=user_id)

    def issue_opened(self, task_id: str, issue_number: int, issue_url: str) -> None:
        _emit(
            task_id, "pm", "issue_opened", f"issue #{issue_number}",
            issue_number=str(issue_number), issue_url=issue_url,
        )

    def step_started(self, task_id: str, order: int, role: str, description: str) -> None:
        _emit(task_id, role, "step_started", f"step {order}: {description[:100]}", order=str(order))

    def step_finished(
        self, task_id: str, order: int, role: str, ok: bool, detail: str,
        *, output: str = "",
    ) -> None:
        status = "step_ok" if ok else "step_failed"
        _emit(task_id, role, status, f"step {order}: {detail[:100]}", order=str(order))

    def task_finished(self, task_id: str, *, closed: bool, ok: bool, note: str) -> None:
        status = "closed" if closed else ("done" if ok else "failed")
        _emit(task_id, "pm", status, note[:200])


async def recent_task_events(limit: int = 100) -> list[dict[str, str]]:
    """Read recent task events (newest first) from the Redis events stream.

    Uses the async client since the /tasks endpoint is async. Best-effort: an
    unreachable Redis yields an empty list rather than failing the request.
    """
    from app.adapters.redis_client import get_client

    try:
        client = get_client()
        entries = await client.xrevrange(k_task_events(), count=max(1, limit))
    except Exception as exc:
        logger.warning("task events read failed: %s", exc)
        return []

    out: list[dict[str, str]] = []
    for entry_id, fields in entries:
        row = {str(k): str(v) for k, v in fields.items()}
        row["id"] = str(entry_id)
        out.append(row)
    return out


def latest_task_states(events: list[dict[str, str]]) -> list[dict[str, str]]:
    """Collapse the event log into one row per task_id (its most recent event).

    Events arrive newest-first, so the first time we see a task_id is its latest
    state — exactly what a board wants to show.
    """
    seen: dict[str, dict[str, str]] = {}
    for ev in events:
        tid = ev.get("task_id", "")
        if tid and tid not in seen:
            seen[tid] = ev
    return list(seen.values())
