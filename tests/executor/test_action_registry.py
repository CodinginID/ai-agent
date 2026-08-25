"""ActionRegistry approval chokepoint (Fase 0)."""

from __future__ import annotations

import pytest

from app.domain.exceptions import ActionExecutionError
from app.executor.actions import ActionMeta, ActionRegistry


def _reg(requires_approval: bool) -> ActionRegistry:
    r = ActionRegistry()
    r.register(ActionMeta(
        name="docker_restart",
        description="restart container",
        risk_level="medium",
        requires_approval=requires_approval,
        handler=lambda ctx: "done",
    ))
    return r


def test_requires_approval_action_blocked_without_approval() -> None:
    r = _reg(requires_approval=True)
    with pytest.raises(ActionExecutionError, match="approval"):
        r.execute("docker_restart", {})


def test_requires_approval_action_runs_when_approved() -> None:
    r = _reg(requires_approval=True)
    assert r.execute("docker_restart", {}, approved=True) == "done"


def test_low_risk_action_runs_without_approval() -> None:
    r = _reg(requires_approval=False)
    assert r.execute("docker_restart", {}) == "done"


def test_unregistered_action_raises() -> None:
    r = ActionRegistry()
    with pytest.raises(ActionExecutionError, match="tidak terdaftar"):
        r.execute("nope", {})
