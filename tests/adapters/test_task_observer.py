"""Unit tests for task observability — LoggingTaskObserver + board helpers (PR-5).

Redis sync/async clients are faked; we verify events are appended with the
right structured fields, that a failing Redis never raises, and that the board
helpers collapse the event log to one row per task (latest state).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.adapters import task_observer as obs
from app.adapters.task_observer import (
    LoggingTaskObserver,
    latest_task_states,
)


class FakeSyncRedis:
    def __init__(self) -> None:
        self.added: list[tuple[str, dict[str, str]]] = []

    def xadd(self, key: str, fields: dict[str, str], maxlen: int = 0, approximate: bool = True) -> str:
        self.added.append((key, dict(fields)))
        return f"{len(self.added)}-0"


class BrokenSyncRedis:
    def xadd(self, *a: Any, **k: Any) -> str:
        raise RuntimeError("redis down")


@pytest.fixture
def fake_sync(monkeypatch: pytest.MonkeyPatch) -> FakeSyncRedis:
    f = FakeSyncRedis()
    monkeypatch.setattr(obs, "get_sync_client", lambda: f)
    return f


def test_task_started_emits_event(fake_sync: FakeSyncRedis) -> None:
    LoggingTaskObserver().task_started("t1", "u1", "build the thing")
    assert len(fake_sync.added) == 1
    key, fields = fake_sync.added[0]
    assert key == "task:events"
    assert fields["task_id"] == "t1"
    assert fields["status"] == "started"
    assert fields["role"] == "pm"
    assert fields["user_id"] == "u1"


def test_issue_opened_carries_issue_fields(fake_sync: FakeSyncRedis) -> None:
    LoggingTaskObserver().issue_opened("t1", 42, "https://gh/issues/42")
    _, fields = fake_sync.added[0]
    assert fields["issue_number"] == "42"
    assert fields["issue_url"] == "https://gh/issues/42"
    assert fields["status"] == "issue_opened"


def test_step_finished_status_reflects_ok(fake_sync: FakeSyncRedis) -> None:
    o = LoggingTaskObserver()
    o.step_finished("t1", 1, "engineer", True, "done")
    o.step_finished("t1", 2, "infra", False, "boom")
    assert fake_sync.added[0][1]["status"] == "step_ok"
    assert fake_sync.added[1][1]["status"] == "step_failed"


def test_task_finished_status_variants(fake_sync: FakeSyncRedis) -> None:
    o = LoggingTaskObserver()
    o.task_finished("a", closed=True, ok=True, note="completed")
    o.task_finished("b", closed=False, ok=True, note="done no issue")
    o.task_finished("c", closed=False, ok=False, note="stopped")
    assert fake_sync.added[0][1]["status"] == "closed"
    assert fake_sync.added[1][1]["status"] == "done"
    assert fake_sync.added[2][1]["status"] == "failed"


def test_emit_swallows_redis_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obs, "get_sync_client", lambda: BrokenSyncRedis())
    # Must not raise — observability is best-effort.
    LoggingTaskObserver().task_started("t1", "u1", "x")


def test_latest_task_states_collapses_to_one_row_per_task() -> None:
    # Newest-first event log (as xrevrange returns).
    events = [
        {"task_id": "t1", "status": "closed", "id": "5-0"},
        {"task_id": "t2", "status": "step_ok", "id": "4-0"},
        {"task_id": "t1", "status": "step_ok", "id": "3-0"},
        {"task_id": "t1", "status": "started", "id": "2-0"},
        {"task_id": "t2", "status": "started", "id": "1-0"},
    ]
    states = latest_task_states(events)
    by_task = {s["task_id"]: s["status"] for s in states}
    assert by_task == {"t1": "closed", "t2": "step_ok"}
    assert len(states) == 2


def test_latest_task_states_ignores_blank_task_id() -> None:
    events = [{"task_id": "", "status": "x", "id": "1-0"}]
    assert latest_task_states(events) == []
