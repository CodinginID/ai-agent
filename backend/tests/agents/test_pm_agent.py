"""Unit tests for app/agents/pm.py — AI provider is mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.agents.pm import PMAgent, TaskPlan, TaskStep


def _make_agent(response: str) -> PMAgent:
    """Build a PMAgent with a mock AI provider that returns *response*."""
    ai = MagicMock()
    ai.chat.return_value = response
    return PMAgent(ai_provider=ai)


# ── Happy path ─────────────────────────────────────────────────────────────────

def test_plan_parses_valid_json_response() -> None:
    payload = json.dumps({
        "title": "Check server status",
        "summary": "We check server health then report",
        "estimated_complexity": "simple",
        "steps": [
            {"order": 1, "description": "Get status", "action": "server_status", "params": {}},
        ],
    })
    agent = _make_agent(payload)
    plan = agent.plan("check the server")

    assert isinstance(plan, TaskPlan)
    assert plan.title == "Check server status"
    assert plan.estimated_complexity == "simple"
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "server_status"


def test_plan_parses_json_embedded_in_prose() -> None:
    """Model sometimes wraps JSON in markdown or adds preamble text."""
    payload = (
        "Here is the plan:\n\n"
        + json.dumps({
            "title": "Git ops",
            "summary": "Run git tasks",
            "estimated_complexity": "medium",
            "steps": [
                {"order": 1, "description": "Status", "action": "git_status", "params": {}},
                {"order": 2, "description": "Diff", "action": "git_diff", "params": {"staged": True}},
            ],
        })
        + "\n\nDone."
    )
    agent = _make_agent(payload)
    plan = agent.plan("show git diff")

    assert len(plan.steps) == 2
    assert plan.steps[1].params == {"staged": True}


def test_plan_step_order_preserved() -> None:
    payload = json.dumps({
        "title": "Multi step",
        "summary": "many steps",
        "estimated_complexity": "complex",
        "steps": [
            {"order": 3, "description": "Push", "action": "git_push", "params": {}},
            {"order": 1, "description": "Add", "action": "git_add", "params": {}},
            {"order": 2, "description": "Commit", "action": "git_commit", "params": {"message": "x"}},
        ],
    })
    agent = _make_agent(payload)
    plan = agent.plan("commit and push")

    orders = [s.order for s in plan.steps]
    assert orders == [3, 1, 2]  # parsed in response order, not sorted


# ── Fallback behaviour ─────────────────────────────────────────────────────────

def test_plan_falls_back_when_no_json() -> None:
    agent = _make_agent("Sorry, I cannot understand that request.")
    plan = agent.plan("do something")

    assert plan.title == "Direct response"
    assert plan.steps == []
    assert plan.estimated_complexity == "simple"


def test_plan_falls_back_when_json_malformed() -> None:
    agent = _make_agent("{not: valid json!!!}")
    plan = agent.plan("do something")

    assert plan.steps == []


def test_plan_falls_back_when_ai_raises() -> None:
    ai = MagicMock()
    ai.chat.side_effect = RuntimeError("Ollama unavailable")
    agent = PMAgent(ai_provider=ai)
    plan = agent.plan("check ram")

    assert "gagal" in plan.summary.lower()
    assert plan.steps == []


# ── Prompt construction ────────────────────────────────────────────────────────

def test_plan_passes_request_and_context_to_ai() -> None:
    ai = MagicMock()
    ai.chat.return_value = "{}"
    agent = PMAgent(ai_provider=ai)
    agent.plan("deploy to prod", context="branch=main")

    call_prompt: str = ai.chat.call_args[0][0]
    assert "deploy to prod" in call_prompt
    assert "branch=main" in call_prompt


def test_plan_includes_available_actions_in_prompt() -> None:
    ai = MagicMock()
    ai.chat.return_value = "{}"
    agent = PMAgent(ai_provider=ai)
    agent.plan("list files")

    call_prompt: str = ai.chat.call_args[0][0]
    assert "file_list" in call_prompt
    assert "git_status" in call_prompt


# ── TaskStep immutability ──────────────────────────────────────────────────────

def test_task_step_is_frozen() -> None:
    step = TaskStep(order=1, description="test", action="git_status", params={})
    with pytest.raises((AttributeError, TypeError)):
        step.order = 2  # type: ignore[misc]


def test_task_plan_is_frozen() -> None:
    plan = TaskPlan(title="t", summary="s", steps=[], estimated_complexity="simple")
    with pytest.raises((AttributeError, TypeError)):
        plan.title = "changed"  # type: ignore[misc]
