from __future__ import annotations

from pathlib import Path

import pytest

from app.memory.context_store import ProjectContextStore, TaskNotFoundError

KEY = "user-1"


@pytest.fixture
def store(tmp_path: Path) -> ProjectContextStore:
    return ProjectContextStore(tmp_path)


# ── decisions ────────────────────────────────────────────────────────────────


def test_add_decision_returns_decision_with_id_and_timestamp(store: ProjectContextStore) -> None:
    decision = store.add_decision(KEY, "pakai Postgres untuk vector store")
    assert decision.text == "pakai Postgres untuk vector store"
    assert decision.id
    assert decision.created_at


def test_list_decisions_returns_most_recent_first(store: ProjectContextStore) -> None:
    store.add_decision(KEY, "first")
    store.add_decision(KEY, "second")
    texts = [d.text for d in store.list_decisions(KEY)]
    assert texts == ["second", "first"]


def test_list_decisions_respects_limit(store: ProjectContextStore) -> None:
    for i in range(5):
        store.add_decision(KEY, f"d{i}")
    assert len(store.list_decisions(KEY, limit=2)) == 2


def test_decisions_survive_new_store_instance(store: ProjectContextStore, tmp_path: Path) -> None:
    store.add_decision(KEY, "persisted decision")
    reopened = ProjectContextStore(tmp_path)
    assert [d.text for d in reopened.list_decisions(KEY)] == ["persisted decision"]


# ── tasks ────────────────────────────────────────────────────────────────────


def test_add_task_defaults_to_open(store: ProjectContextStore) -> None:
    task = store.add_task(KEY, "deploy ke staging")
    assert task.status == "open"
    assert task.text == "deploy ke staging"
    assert task.id


def test_task_ids_are_sequential_per_namespace(store: ProjectContextStore) -> None:
    first = store.add_task(KEY, "a")
    second = store.add_task(KEY, "b")
    assert first.id == "1"
    assert second.id == "2"


def test_list_tasks_returns_all_in_creation_order(store: ProjectContextStore) -> None:
    store.add_task(KEY, "a")
    store.add_task(KEY, "b")
    assert [t.text for t in store.list_tasks(KEY)] == ["a", "b"]


def test_complete_task_marks_done(store: ProjectContextStore) -> None:
    task = store.add_task(KEY, "a")
    done = store.complete_task(KEY, task.id)
    assert done.status == "done"
    assert done.done_at
    assert store.list_tasks(KEY)[0].status == "done"


def test_complete_unknown_task_raises(store: ProjectContextStore) -> None:
    with pytest.raises(TaskNotFoundError):
        store.complete_task(KEY, "999")


def test_tasks_survive_new_store_instance(store: ProjectContextStore, tmp_path: Path) -> None:
    task = store.add_task(KEY, "persisted task")
    store.complete_task(KEY, task.id)
    reopened = ProjectContextStore(tmp_path)
    persisted = reopened.list_tasks(KEY)
    assert len(persisted) == 1
    assert persisted[0].status == "done"


# ── notes (/remember) ────────────────────────────────────────────────────────


def test_add_note_and_list_most_recent_first(store: ProjectContextStore) -> None:
    store.add_note(KEY, "domain production: example.com")
    store.add_note(KEY, "ssh port 2222")
    assert [n.text for n in store.list_notes(KEY)] == ["ssh port 2222", "domain production: example.com"]


# ── executions ───────────────────────────────────────────────────────────────


def test_add_execution_and_list(store: ProjectContextStore) -> None:
    store.add_execution(KEY, "deploy", "ok")
    rows = store.list_executions(KEY)
    assert rows[0].summary == "deploy"
    assert rows[0].status == "ok"


# ── namespace isolation ──────────────────────────────────────────────────────


def test_namespaces_are_isolated(store: ProjectContextStore) -> None:
    store.add_decision("user-1", "a")
    store.add_decision("user-2", "b")
    assert [d.text for d in store.list_decisions("user-1")] == ["a"]
    assert [d.text for d in store.list_decisions("user-2")] == ["b"]


def test_namespace_with_unsafe_chars_does_not_escape_data_dir(
    store: ProjectContextStore, tmp_path: Path
) -> None:
    store.add_decision("../../etc/passwd", "evil")
    # No file should be written outside the data dir.
    assert not (tmp_path.parent.parent / "etc").exists()


# ── build_context (prompt injection source) ──────────────────────────────────


def test_build_context_empty_returns_empty_string(store: ProjectContextStore) -> None:
    assert store.build_context(KEY) == ""


def test_build_context_includes_open_tasks_and_recent_decisions(store: ProjectContextStore) -> None:
    store.add_decision(KEY, "pakai Postgres")
    store.add_task(KEY, "fix login bug")
    note = store.add_note(KEY, "domain: example.com")
    ctx = store.build_context(KEY)
    assert "pakai Postgres" in ctx
    assert "fix login bug" in ctx
    assert "example.com" in ctx
    assert note.id  # sanity


def test_build_context_excludes_completed_tasks(store: ProjectContextStore) -> None:
    task = store.add_task(KEY, "already done task")
    store.complete_task(KEY, task.id)
    assert "already done task" not in store.build_context(KEY)


def test_build_context_respects_max_chars(store: ProjectContextStore) -> None:
    for i in range(200):
        store.add_note(KEY, f"note number {i} with some padding text")
    ctx = store.build_context(KEY, max_chars=500)
    assert len(ctx) <= 500
