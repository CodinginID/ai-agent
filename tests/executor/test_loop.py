"""Tests for ExecutionLoop — observe/think/decide/execute/reflect/retry cycle.

All external calls (AI provider, subprocess) are mocked.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.executor.context import ContextCollector, EnvironmentContext
from app.executor.loop import (
    ExecutionLoop,
    LoopEvent,
    ReflectionResult,
    _execute_file_read,
    _parse_decision,
    _parse_reflection,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _stub_env() -> EnvironmentContext:
    return EnvironmentContext(
        git_status="M app/bot.py",
        docker_ps="bot   Up",
        repo_files="app/bot.py",
        hostname="test-host",
        working_dir="/tmp",
        collected_at=datetime.now(),
    )


def _make_collector() -> ContextCollector:
    collector = MagicMock(spec=ContextCollector)
    collector.collect.return_value = _stub_env()
    return collector


def _make_loop(ai_responses: list[str], tmp_path: Path) -> ExecutionLoop:
    ai = MagicMock()
    ai.chat.side_effect = ai_responses
    collector = _make_collector()
    return ExecutionLoop(ai=ai, context_collector=collector, working_dir=tmp_path)


def _collect_events(loop: ExecutionLoop, prompt: str) -> list[LoopEvent]:
    return list(loop.run(prompt))


# ── _parse_decision tests ────────────────────────────────────────────────────

def test_parse_decision_terminal_action() -> None:
    raw = '{"action": "terminal", "command": "docker ps -a"}'
    decision = _parse_decision(raw)
    assert decision.action == "terminal"
    assert decision.command == "docker ps -a"


def test_parse_decision_respond_action() -> None:
    raw = '{"action": "respond", "text": "All containers are running."}'
    decision = _parse_decision(raw)
    assert decision.action == "respond"
    assert decision.text == "All containers are running."


def test_parse_decision_file_read_action() -> None:
    raw = '{"action": "file_read", "path": "/etc/hostname"}'
    decision = _parse_decision(raw)
    assert decision.action == "file_read"
    assert decision.path == "/etc/hostname"


def test_parse_decision_multi_step_action() -> None:
    raw = '{"action": "multi_step", "steps": ["git status", "docker ps"]}'
    decision = _parse_decision(raw)
    assert decision.action == "multi_step"
    assert decision.steps == ["git status", "docker ps"]


def test_parse_decision_plain_text_fallback() -> None:
    """LLM returns plain text — treat as respond action."""
    raw = "The server is fine."
    decision = _parse_decision(raw)
    assert decision.action == "respond"
    assert decision.text == "The server is fine."


def test_parse_decision_invalid_json_fallback() -> None:
    raw = "not valid json at all {broken"
    decision = _parse_decision(raw)
    assert decision.action == "respond"


# ── _parse_reflection tests ──────────────────────────────────────────────────

def test_parse_reflection_satisfied_true() -> None:
    raw = '{"satisfied": true}'
    result = _parse_reflection(raw)
    assert result.satisfied is True


def test_parse_reflection_satisfied_false_with_reason() -> None:
    raw = json.dumps({
        "satisfied": False,
        "reason": "Only showed running containers, not stopped ones.",
        "next_action": {"action": "terminal", "command": "docker ps -a"},
    })
    result = _parse_reflection(raw)
    assert result.satisfied is False
    assert "stopped" in result.reason
    assert result.next_action["command"] == "docker ps -a"


def test_parse_reflection_invalid_json_assumes_satisfied() -> None:
    result = _parse_reflection("garbage text")
    assert result.satisfied is True


# ── LoopEvent validation ──────────────────────────────────────────────────────

def test_loop_event_raises_on_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unknown LoopEvent type"):
        LoopEvent(type="invalid_type")


def test_loop_event_valid_types_accepted() -> None:
    for t in ("observing", "thinking", "action_started", "action_result",
              "reflecting", "retrying", "text_chunk", "final", "error"):
        ev = LoopEvent(type=t, data={})
        assert ev.type == t


# ── ExecutionLoop.run tests ───────────────────────────────────────────────────

def test_run_respond_action_emits_final_event(tmp_path: Path) -> None:
    """LLM immediately responds with a text action — no tool execution."""
    loop = _make_loop(
        ai_responses=['{"action": "respond", "text": "Server is running fine."}'],
        tmp_path=tmp_path,
    )
    events = _collect_events(loop, "Is the server OK?")
    types = [e.type for e in events]
    assert "observing" in types
    assert "thinking" in types
    assert "final" in types
    final = next(e for e in events if e.type == "final")
    assert "Server is running fine." in final.data["text"]


def test_run_terminal_action_satisfied_on_first_attempt(tmp_path: Path) -> None:
    """LLM picks terminal action, reflection says satisfied → no retry."""
    loop = _make_loop(
        ai_responses=[
            '{"action": "terminal", "command": "docker ps"}',   # think
            '{"satisfied": true}',                               # reflect
            "Docker shows 2 containers running.",                # final synthesis
        ],
        tmp_path=tmp_path,
    )
    with patch("app.executor.loop._execute_terminal", return_value=("container1\ncontainer2", 0)):
        events = _collect_events(loop, "Show docker containers")

    types = [e.type for e in events]
    assert "observing" in types
    assert "action_started" in types
    assert "action_result" in types
    assert "reflecting" in types
    assert "final" in types
    assert "retrying" not in types


def test_run_retries_when_reflection_unsatisfied(tmp_path: Path) -> None:
    """LLM says not satisfied → loop retries with next_action context."""
    loop = _make_loop(
        ai_responses=[
            '{"action": "terminal", "command": "docker ps"}',          # think attempt 1
            json.dumps({                                                 # reflect attempt 1
                "satisfied": False,
                "reason": "Need to also check stopped containers",
                "next_action": {"action": "terminal", "command": "docker ps -a"},
            }),
            '{"action": "terminal", "command": "docker ps -a"}',       # think attempt 2
            '{"satisfied": true}',                                      # reflect attempt 2
            "All containers listed including stopped ones.",            # synthesis
        ],
        tmp_path=tmp_path,
    )
    with patch("app.executor.loop._execute_terminal", return_value=("output", 0)):
        events = _collect_events(loop, "Show all docker containers including stopped")

    types = [e.type for e in events]
    assert "retrying" in types
    retrying_ev = next(e for e in events if e.type == "retrying")
    assert retrying_ev.data["attempt"] == 1


def test_run_stops_at_max_retries(tmp_path: Path) -> None:
    """Loop stops after MAX_RETRIES even if never satisfied."""
    from app.executor.loop import MAX_RETRIES
    unsatisfied = json.dumps({
        "satisfied": False,
        "reason": "still not enough info",
    })
    # think + reflect pairs for MAX_RETRIES, plus one final synthesis
    responses = []
    for _ in range(MAX_RETRIES):
        responses.append('{"action": "terminal", "command": "ls"}')
        responses.append(unsatisfied)
    responses.append("Final answer after retries.")

    loop = _make_loop(ai_responses=responses, tmp_path=tmp_path)
    with patch("app.executor.loop._execute_terminal", return_value=("output", 0)):
        events = _collect_events(loop, "complex request")

    retrying_events = [e for e in events if e.type == "retrying"]
    # Should not exceed MAX_RETRIES - 1 retrying events (last iteration doesn't retry)
    assert len(retrying_events) <= MAX_RETRIES - 1


def test_run_file_read_action(tmp_path: Path) -> None:
    """LLM picks file_read action — reads a real temp file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello from file")

    loop = _make_loop(
        ai_responses=[
            json.dumps({"action": "file_read", "path": str(test_file)}),
            '{"satisfied": true}',
            "File content: hello from file",
        ],
        tmp_path=tmp_path,
    )
    events = _collect_events(loop, f"Read the file {test_file}")

    types = [e.type for e in events]
    assert "action_result" in types
    result_ev = next(e for e in events if e.type == "action_result")
    assert "hello from file" in result_ev.data["output"]


def test_run_emits_error_on_ai_failure(tmp_path: Path) -> None:
    """If AI raises, loop emits error event."""
    ai = MagicMock()
    ai.chat.side_effect = ConnectionError("Ollama unreachable")
    collector = _make_collector()
    loop = ExecutionLoop(ai=ai, context_collector=collector, working_dir=tmp_path)

    events = _collect_events(loop, "what is the server status?")
    types = [e.type for e in events]
    assert "error" in types
    error_ev = next(e for e in events if e.type == "error")
    assert "AI think failed" in error_ev.data["message"]


# ── _execute_file_read tests ──────────────────────────────────────────────────

def test_execute_file_read_returns_content(tmp_path: Path) -> None:
    f = tmp_path / "sample.txt"
    f.write_text("line one\nline two")
    result = _execute_file_read(str(f))
    assert "line one" in result
    assert "line two" in result


def test_execute_file_read_missing_file() -> None:
    result = _execute_file_read("/nonexistent/path/file.txt")
    assert "not found" in result


def test_execute_file_read_caps_at_100_lines(tmp_path: Path) -> None:
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"line {i}" for i in range(200)))
    result = _execute_file_read(str(f))
    assert "showing first 100" in result
