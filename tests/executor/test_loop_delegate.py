"""Tests for ExecutionLoop delegate action (loop ↔ worker unification, PR-1).

Worker dispatch is mocked via a fake WorkerDispatchPort — no real WS/worker.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from app.executor.context import ContextCollector, EnvironmentContext
from app.executor.loop import ExecutionLoop, _parse_decision
from app.ports.worker_dispatch import DispatchResult

# ── Helpers ───────────────────────────────────────────────────────────────────

def _stub_env() -> EnvironmentContext:
    return EnvironmentContext(
        git_status="clean",
        docker_ps="bot Up",
        repo_files="app/bot.py",
        hostname="test-host",
        working_dir="/tmp",
        collected_at=datetime.now(),
    )


def _make_collector() -> ContextCollector:
    collector = MagicMock(spec=ContextCollector)
    collector.collect.return_value = _stub_env()
    return collector


class _FakeDispatcher:
    """Records calls and returns a canned DispatchResult."""

    def __init__(self, result: DispatchResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str, str]] = []

    def dispatch(self, user_id: str, role: str, prompt: str) -> DispatchResult:
        self.calls.append((user_id, role, prompt))
        return self.result


def _make_loop(
    ai_responses: list[str],
    tmp_path: Path,
    dispatcher: object | None = None,
) -> ExecutionLoop:
    ai = MagicMock()
    ai.chat.side_effect = ai_responses
    return ExecutionLoop(
        ai=ai,
        context_collector=_make_collector(),
        working_dir=tmp_path,
        worker_dispatch=dispatcher,  # type: ignore[arg-type]
    )


# ── _parse_decision: delegate ─────────────────────────────────────────────────

def test_parse_decision_delegate_action() -> None:
    raw = '{"action": "delegate", "role": "engineer", "prompt": "refactor auth module"}'
    decision = _parse_decision(raw)
    assert decision.action == "delegate"
    assert decision.role == "engineer"
    assert decision.delegate_prompt == "refactor auth module"


# ── delegate execution path ────────────────────────────────────────────────────

def test_delegate_dispatches_to_worker_and_finalizes(tmp_path: Path) -> None:
    dispatcher = _FakeDispatcher(
        DispatchResult(output="diff applied: 3 files", summary="exit 0", ok=True),
    )
    loop = _make_loop(
        ai_responses=[
            '{"action": "delegate", "role": "engineer", "prompt": "refactor X"}',  # think
            '{"satisfied": true}',                                                  # reflect
            "Worker refactored 3 files successfully.",                              # synthesis
        ],
        tmp_path=tmp_path,
        dispatcher=dispatcher,
    )
    events = list(loop.run("refactor the X module", user_id="user-1"))
    types = [e.type for e in events]

    assert "action_started" in types
    assert "action_result" in types
    assert "final" in types or any(e.type == "text_chunk" for e in events)

    # Dispatcher was called with the right role + prompt + user.
    assert dispatcher.calls == [("user-1", "engineer", "refactor X")]

    result_ev = next(e for e in events if e.type == "action_result")
    assert result_ev.data["action"] == "delegate"
    assert "diff applied" in result_ev.data["output"]


def test_delegate_without_dispatcher_degrades_gracefully(tmp_path: Path) -> None:
    """No dispatcher wired → delegate yields an error-ish result, loop survives."""
    loop = _make_loop(
        ai_responses=[
            '{"action": "delegate", "role": "engineer", "prompt": "do work"}',
            "Could not delegate; no worker available.",  # synthesis (reflect skipped at max? no)
            '{"satisfied": true}',
            "final answer",
        ],
        tmp_path=tmp_path,
        dispatcher=None,
    )
    events = list(loop.run("delegate something", user_id="user-1"))
    result_ev = next(e for e in events if e.type == "action_result")
    assert result_ev.data["action"] == "delegate"
    assert "unavailable" in result_ev.data["output"]
    # Loop must not crash — at least one terminal-ish event present.
    assert any(e.type in ("final", "text_chunk", "error") for e in events)


def test_delegate_missing_user_id_degrades(tmp_path: Path) -> None:
    dispatcher = _FakeDispatcher(DispatchResult(output="x", ok=True))
    loop = _make_loop(
        ai_responses=[
            '{"action": "delegate", "role": "engineer", "prompt": "do work"}',
            '{"satisfied": true}',
            "final",
        ],
        tmp_path=tmp_path,
        dispatcher=dispatcher,
    )
    events = list(loop.run("delegate", user_id=""))  # no user_id
    result_ev = next(e for e in events if e.type == "action_result")
    assert "unavailable" in result_ev.data["output"]
    # Dispatcher never called because user_id missing.
    assert dispatcher.calls == []


def test_delegate_worker_error_surfaced(tmp_path: Path) -> None:
    dispatcher = _FakeDispatcher(
        DispatchResult(output="", ok=False, error="no worker online"),
    )
    loop = _make_loop(
        ai_responses=[
            '{"action": "delegate", "role": "reviewer", "prompt": "review PR"}',
            '{"satisfied": true}',
            "Could not complete: worker offline.",
        ],
        tmp_path=tmp_path,
        dispatcher=dispatcher,
    )
    events = list(loop.run("review the PR", user_id="user-9"))
    result_ev = next(e for e in events if e.type == "action_result")
    assert "no worker online" in result_ev.data["output"]
    assert result_ev.data["exit_code"] == -1


def test_delegate_dispatcher_exception_does_not_crash_loop(tmp_path: Path) -> None:
    boom = MagicMock()
    boom.dispatch.side_effect = RuntimeError("kaboom")
    loop = _make_loop(
        ai_responses=[
            '{"action": "delegate", "role": "engineer", "prompt": "x"}',
            '{"satisfied": true}',
            "final synthesis",
        ],
        tmp_path=tmp_path,
        dispatcher=boom,
    )
    events = list(loop.run("delegate", user_id="user-1"))
    types = [e.type for e in events]
    # Loop continued past the failure to synthesis (no uncaught crash).
    assert "action_result" in types
    result_ev = next(e for e in events if e.type == "action_result")
    assert "delegate failed" in result_ev.data["output"]


# ── DispatchResult value object ─────────────────────────────────────────────────

def test_dispatch_result_defaults() -> None:
    r = DispatchResult(output="hello")
    assert r.output == "hello"
    assert r.ok is True
    assert r.summary == ""
    assert r.error == ""
