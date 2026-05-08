"""Unit tests for app/domain/agents.py — readiness_message and existing helpers."""

from __future__ import annotations

from app.domain.agents import (
    AgentCapability,
    AgentRoleAssignment,
    agent_status_detail,
    readiness_message,
    resolve_agent_roles,
)


def _cap(agent_id: str, *, enabled: bool, available: bool) -> AgentCapability:
    return AgentCapability(
        agent_id=agent_id,
        display_name=agent_id,
        provider="test",
        role_hint="engineer",
        enabled=enabled,
        available=available,
    )


# ── agent_status_detail ───────────────────────────────────────────────────────

def test_status_detail_ready() -> None:
    cap = _cap("claude", enabled=True, available=True)
    assert agent_status_detail(cap) == "enabled and available"


def test_status_detail_available_but_disabled() -> None:
    cap = _cap("claude", enabled=False, available=True)
    assert "disabled" in agent_status_detail(cap)


def test_status_detail_enabled_but_missing() -> None:
    cap = _cap("claude", enabled=True, available=False)
    assert "missing" in agent_status_detail(cap)


def test_status_detail_fully_missing() -> None:
    cap = _cap("claude", enabled=False, available=False)
    detail = agent_status_detail(cap)
    assert "disabled" in detail and "missing" in detail


# ── resolve_agent_roles ───────────────────────────────────────────────────────

def test_resolve_roles_ready_agent() -> None:
    caps = [_cap("claude", enabled=True, available=True)]
    result = resolve_agent_roles(caps, {"reviewer": "claude"})
    assert len(result) == 1
    assert result[0].ready is True
    assert result[0].role == "reviewer"


def test_resolve_roles_unknown_agent() -> None:
    result = resolve_agent_roles([], {"engineer": "ghost"})
    assert result[0].status == "unknown_agent"
    assert result[0].ready is False


def test_resolve_roles_empty_assignments() -> None:
    caps = [_cap("codex", enabled=True, available=True)]
    assert resolve_agent_roles(caps, {}) == ()


# ── readiness_message ─────────────────────────────────────────────────────────

def test_readiness_message_no_assignments() -> None:
    msg = readiness_message(())
    assert "No agents" in msg


def test_readiness_message_all_ready() -> None:
    assignments = (
        AgentRoleAssignment(role="engineer", agent_id="codex", ready=True, status="ready", detail=""),
    )
    msg = readiness_message(assignments)
    assert "1 agent(s) ready" in msg
    assert "codex" in msg


def test_readiness_message_all_not_ready() -> None:
    assignments = (
        AgentRoleAssignment(role="engineer", agent_id="codex", ready=False, status="enabled_missing", detail=""),
    )
    msg = readiness_message(assignments)
    assert "not ready" in msg
    assert "codex" in msg


def test_readiness_message_mixed() -> None:
    assignments = (
        AgentRoleAssignment(role="engineer", agent_id="codex", ready=True, status="ready", detail=""),
        AgentRoleAssignment(role="reviewer", agent_id="claude", ready=False, status="enabled_missing", detail=""),
    )
    msg = readiness_message(assignments)
    assert "ready" in msg
    assert "not ready" in msg
    assert "codex" in msg
    assert "claude" in msg
