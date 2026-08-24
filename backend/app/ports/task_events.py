"""Port for observing task lifecycle events — structured observability (PR-5).

The TaskRunner emits lifecycle events (plan ready, issue opened, step started /
finished, task closed / failed) through this port. A concrete adapter turns
each into a structured log line ``[TIME][ROLE][TASK_ID][STATUS]`` on stdout
(captured by ``docker logs``) and an entry on the Redis audit stream (read back
by ``GET /tasks``).

Keeping it a Protocol means the orchestrator never imports the audit adapter —
domain depends on the port, and tests inject a recording fake or the no-op.
"""

from __future__ import annotations

from typing import Protocol


class TaskObserver(Protocol):
    def task_started(self, task_id: str, user_id: str, request: str) -> None: ...

    def issue_opened(self, task_id: str, issue_number: int, issue_url: str) -> None: ...

    def step_started(
        self, task_id: str, order: int, role: str, description: str,
    ) -> None: ...

    def step_finished(
        self, task_id: str, order: int, role: str, ok: bool, detail: str,
    ) -> None: ...

    def task_finished(
        self, task_id: str, *, closed: bool, ok: bool, note: str,
    ) -> None: ...


class NullTaskObserver:
    """No-op observer — the default so TaskRunner works without wiring."""

    def task_started(self, task_id: str, user_id: str, request: str) -> None:
        return None

    def issue_opened(self, task_id: str, issue_number: int, issue_url: str) -> None:
        return None

    def step_started(self, task_id: str, order: int, role: str, description: str) -> None:
        return None

    def step_finished(self, task_id: str, order: int, role: str, ok: bool, detail: str) -> None:
        return None

    def task_finished(self, task_id: str, *, closed: bool, ok: bool, note: str) -> None:
        return None
