"""Guard-rail logic for the project-context TUI commands.

Behavior against the backend is covered by tests/interfaces/test_context_endpoints.py;
here we only assert the pure argument validation that runs BEFORE any HTTP call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.tui._commands as cmds


@pytest.fixture(autouse=True)
def _silence_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmds, "println", MagicMock())
    monkeypatch.setattr(cmds, "print_parts", MagicMock())


@pytest.mark.asyncio
async def test_remember_without_text_skips_request(monkeypatch: pytest.MonkeyPatch) -> None:
    req = AsyncMock()
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_remember([])
    req.assert_not_called()


@pytest.mark.asyncio
async def test_decision_without_text_skips_request(monkeypatch: pytest.MonkeyPatch) -> None:
    req = AsyncMock()
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_decision([])
    req.assert_not_called()


@pytest.mark.asyncio
async def test_task_add_without_text_skips_request(monkeypatch: pytest.MonkeyPatch) -> None:
    req = AsyncMock()
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_task_add([])
    req.assert_not_called()


@pytest.mark.asyncio
async def test_task_done_without_id_skips_request(monkeypatch: pytest.MonkeyPatch) -> None:
    req = AsyncMock()
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_task_done([])
    req.assert_not_called()


@pytest.mark.asyncio
async def test_remember_with_text_posts_to_remember_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    req = AsyncMock(return_value={"id": "x", "text": "hi"})
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_remember(["catat", "ini"])
    req.assert_awaited_once_with("POST", "/context/remember", {"text": "catat ini"})


@pytest.mark.asyncio
async def test_task_done_with_id_posts_to_done_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    req = AsyncMock(return_value={"id": "3", "status": "done"})
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_task_done(["3"])
    req.assert_awaited_once_with("POST", "/context/tasks/3/done")


# ── workflow commands (#6) ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_without_goal_skips_request(monkeypatch: pytest.MonkeyPatch) -> None:
    req = AsyncMock()
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_plan([])
    req.assert_not_called()


@pytest.mark.asyncio
async def test_plan_stores_last_plan_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmds._state, "last_plan_id", None)
    req = AsyncMock(return_value={"plan_id": "abc123", "goal": "g", "steps": ["s"]})
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_plan(["add", "feature"])
    req.assert_awaited_once_with("POST", "/workflow/plan", {"goal": "add feature"})
    assert cmds._state.last_plan_id == "abc123"


@pytest.mark.asyncio
async def test_implement_without_plan_or_last_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmds._state, "last_plan_id", None)
    req = AsyncMock()
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_implement([])
    req.assert_not_called()


@pytest.mark.asyncio
async def test_implement_uses_last_plan_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmds._state, "last_plan_id", "last-1")
    req = AsyncMock(return_value={"approved": True, "revisions": 0, "verdict": {}})
    monkeypatch.setattr(cmds, "_context_request", req)
    await cmds.cmd_implement([])
    req.assert_awaited_once_with("POST", "/workflow/implement", {"plan_id": "last-1"})
