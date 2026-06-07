"""Tests for TaskRunner — PM plan → issue → dispatch → close (PR-4).

GitHub + worker dispatch + PM agent are all mocked.
"""

from __future__ import annotations

import pytest

from app.adapters.github import GitHubIssue
from app.agents.pm import TaskPlan, TaskStep
from app.orchestrator.task_runner import TaskRunner, role_for_action
from app.ports.worker_dispatch import DispatchResult

# ── role_for_action (pure) ──────────────────────────────────────────────────────

def test_role_for_action_file_write_is_engineer() -> None:
    assert role_for_action("file_write") == "engineer"
    assert role_for_action("file_edit") == "engineer"


def test_role_for_action_docker_and_git_are_infra() -> None:
    assert role_for_action("docker_restart") == "infra"
    assert role_for_action("git_commit") == "infra"
    assert role_for_action("terminal") == "infra"


def test_role_for_action_unknown_is_research() -> None:
    assert role_for_action("something_else") == "research"


# ── fakes ────────────────────────────────────────────────────────────────────────

class _FakePM:
    def __init__(self, plan: TaskPlan) -> None:
        self._plan = plan

    def plan(self, request: str, context: str = "") -> TaskPlan:
        return self._plan


class _FakeGitHub:
    def __init__(self) -> None:
        self.created: dict | None = None
        self.comments: list[tuple[int, str]] = []
        self.closed: tuple[int, str] | None = None
        self._n = 0

    async def create_issue(self, title, body="", labels=None):  # type: ignore[no-untyped-def]
        self._n += 1
        self.created = {"title": title, "body": body, "labels": labels}
        return GitHubIssue(number=self._n, title=title, url=f"http://x/{self._n}", state="open")

    async def comment_issue(self, issue_number, body):  # type: ignore[no-untyped-def]
        self.comments.append((issue_number, body))

    async def close_issue(self, issue_number, comment=""):  # type: ignore[no-untyped-def]
        self.closed = (issue_number, comment)


class _FakeDispatch:
    def __init__(self, results: list[DispatchResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, str, str]] = []

    async def dispatch_async(self, user_id, role, prompt):  # type: ignore[no-untyped-def]
        self.calls.append((user_id, role, prompt))
        return self._results.pop(0)


def _plan(steps: list[TaskStep], title="Do the thing") -> TaskPlan:
    return TaskPlan(title=title, summary="because", steps=steps, estimated_complexity="medium")


# ── happy path ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_successful_two_step_task_creates_comments_and_closes() -> None:
    plan = _plan([
        TaskStep(order=1, description="write module", action="file_write", params={}),
        TaskStep(order=2, description="restart service", action="docker_restart", params={}),
    ])
    gh = _FakeGitHub()
    dispatch = _FakeDispatch([
        DispatchResult(output="written", summary="exit 0", ok=True),
        DispatchResult(output="restarted", summary="exit 0", ok=True),
    ])
    runner = TaskRunner(pm=_FakePM(plan), github=gh, dispatch=dispatch)

    result = await runner.run("user-1", "build and restart")

    assert result.ok is True
    assert result.closed is True
    assert gh.created is not None
    assert gh.closed is not None and gh.closed[0] == result.issue_number
    # One comment per step.
    assert len(gh.comments) == 2
    # Roles routed correctly per step action.
    assert dispatch.calls[0][1] == "engineer"   # file_write
    assert dispatch.calls[1][1] == "infra"       # docker_restart


@pytest.mark.asyncio
async def test_steps_executed_in_order() -> None:
    plan = _plan([
        TaskStep(order=2, description="second", action="terminal", params={}),
        TaskStep(order=1, description="first", action="terminal", params={}),
    ])
    gh = _FakeGitHub()
    dispatch = _FakeDispatch([
        DispatchResult(output="a", ok=True),
        DispatchResult(output="b", ok=True),
    ])
    runner = TaskRunner(pm=_FakePM(plan), github=gh, dispatch=dispatch)
    await runner.run("user-1", "ordered")
    # Despite plan order, runner sorts by .order → "first" dispatched first.
    assert dispatch.calls[0][2] == "first"
    assert dispatch.calls[1][2] == "second"


# ── failure path ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failure_stops_and_leaves_issue_open() -> None:
    plan = _plan([
        TaskStep(order=1, description="step one", action="file_write", params={}),
        TaskStep(order=2, description="step two", action="terminal", params={}),
    ])
    gh = _FakeGitHub()
    dispatch = _FakeDispatch([
        DispatchResult(output="", ok=False, error="no worker online"),
    ])
    runner = TaskRunner(pm=_FakePM(plan), github=gh, dispatch=dispatch)

    result = await runner.run("user-1", "will fail")

    assert result.ok is False
    assert result.closed is False
    assert gh.closed is None             # issue stays open
    assert len(gh.comments) == 1         # only the failed step commented
    assert len(dispatch.calls) == 1      # stopped after first failure
    assert "no worker online" in result.note


# ── no-steps path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_steps_does_not_create_issue() -> None:
    plan = _plan([], title="Direct")
    gh = _FakeGitHub()
    dispatch = _FakeDispatch([])
    runner = TaskRunner(pm=_FakePM(plan), github=gh, dispatch=dispatch)

    result = await runner.run("user-1", "just chat")

    assert result.issue_number is None
    assert gh.created is None
    assert result.note == "no steps to execute"


@pytest.mark.asyncio
async def test_issue_body_lists_steps() -> None:
    plan = _plan([
        TaskStep(order=1, description="do X", action="file_write", params={}),
    ])
    gh = _FakeGitHub()
    dispatch = _FakeDispatch([DispatchResult(output="ok", ok=True)])
    runner = TaskRunner(pm=_FakePM(plan), github=gh, dispatch=dispatch)
    await runner.run("user-1", "req")
    assert gh.created is not None
    assert "do X" in gh.created["body"]
    assert "octopus-task" in (gh.created["labels"] or [])


# ── observability (PR-5) ─────────────────────────────────────────────────────────

class _RecordingObserver:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def task_started(self, task_id, user_id, request):  # type: ignore[no-untyped-def]
        self.events.append(("task_started", task_id))

    def issue_opened(self, task_id, issue_number, issue_url):  # type: ignore[no-untyped-def]
        self.events.append(("issue_opened", str(issue_number)))

    def step_started(self, task_id, order, role, description):  # type: ignore[no-untyped-def]
        self.events.append(("step_started", f"{order}:{role}"))

    def step_finished(self, task_id, order, role, ok, detail):  # type: ignore[no-untyped-def]
        self.events.append(("step_finished", f"{order}:{ok}"))

    def task_finished(self, task_id, *, closed, ok, note):  # type: ignore[no-untyped-def]
        self.events.append(("task_finished", f"closed={closed},ok={ok}"))


@pytest.mark.asyncio
async def test_observer_receives_full_lifecycle_on_success() -> None:
    plan = _plan([
        TaskStep(order=1, description="write", action="file_write", params={}),
    ])
    obs = _RecordingObserver()
    runner = TaskRunner(
        pm=_FakePM(plan),
        github=_FakeGitHub(),
        dispatch=_FakeDispatch([DispatchResult(output="ok", ok=True)]),
        observer=obs,
    )
    await runner.run("user-1", "req")
    names = [e[0] for e in obs.events]
    assert names == [
        "task_started", "issue_opened", "step_started", "step_finished", "task_finished",
    ]
    assert obs.events[-1][1] == "closed=True,ok=True"


@pytest.mark.asyncio
async def test_observer_task_finished_on_failure() -> None:
    plan = _plan([
        TaskStep(order=1, description="x", action="file_write", params={}),
    ])
    obs = _RecordingObserver()
    runner = TaskRunner(
        pm=_FakePM(plan),
        github=_FakeGitHub(),
        dispatch=_FakeDispatch([DispatchResult(output="", ok=False, error="boom")]),
        observer=obs,
    )
    await runner.run("user-1", "req")
    assert ("task_finished", "closed=False,ok=False") in obs.events


@pytest.mark.asyncio
async def test_observer_no_steps_still_finishes() -> None:
    obs = _RecordingObserver()
    runner = TaskRunner(
        pm=_FakePM(_plan([], title="Direct")),
        github=_FakeGitHub(),
        dispatch=_FakeDispatch([]),
        observer=obs,
    )
    await runner.run("user-1", "chat")
    names = [e[0] for e in obs.events]
    assert names == ["task_started", "task_finished"]


# ── task-level RAG memory ─────────────────────────────────────────────────────────

class _CapturingPM:
    """PM that records the context it was planned with."""

    def __init__(self, plan: TaskPlan) -> None:
        self._plan = plan
        self.seen_context: str | None = None

    def plan(self, request: str, context: str = "") -> TaskPlan:
        self.seen_context = context
        return self._plan


class _RecordingMemory:
    def __init__(self, recall_value: str) -> None:
        self._recall = recall_value
        self.indexed: list[tuple[str, str, str, str]] = []

    async def recall_for_planning(self, user_id, request, base_context):  # type: ignore[no-untyped-def]
        return self._recall

    async def index_task(self, user_id, request, summary, outcome_note):  # type: ignore[no-untyped-def]
        self.indexed.append((user_id, request, summary, outcome_note))


@pytest.mark.asyncio
async def test_memory_recall_feeds_planning_context() -> None:
    pm = _CapturingPM(_plan([
        TaskStep(order=1, description="x", action="file_write", params={}),
    ]))
    mem = _RecordingMemory("PAST TASK CONTEXT")
    runner = TaskRunner(
        pm=pm,
        github=_FakeGitHub(),
        dispatch=_FakeDispatch([DispatchResult(output="ok", ok=True)]),
        memory=mem,
    )
    await runner.run("user-1", "do it", context="orig")
    assert pm.seen_context == "PAST TASK CONTEXT"


@pytest.mark.asyncio
async def test_memory_indexes_task_on_success() -> None:
    mem = _RecordingMemory("")
    runner = TaskRunner(
        pm=_FakePM(_plan([
            TaskStep(order=1, description="x", action="file_write", params={}),
        ])),
        github=_FakeGitHub(),
        dispatch=_FakeDispatch([DispatchResult(output="ok", ok=True)]),
        memory=mem,
    )
    await runner.run("user-1", "do it")
    assert len(mem.indexed) == 1
    assert mem.indexed[0][0] == "user-1"
    assert mem.indexed[0][1] == "do it"


@pytest.mark.asyncio
async def test_memory_not_indexed_on_failure() -> None:
    mem = _RecordingMemory("")
    runner = TaskRunner(
        pm=_FakePM(_plan([
            TaskStep(order=1, description="x", action="file_write", params={}),
        ])),
        github=_FakeGitHub(),
        dispatch=_FakeDispatch([DispatchResult(output="", ok=False, error="boom")]),
        memory=mem,
    )
    await runner.run("user-1", "do it")
    assert mem.indexed == []   # failed task is not memorized
