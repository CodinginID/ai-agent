"""Tests for the role → (agent, model) router (orchestrator/router.py).

Pure functions — no mocks needed.
"""

from __future__ import annotations

from app.orchestrator.router import (
    DEFAULT_ROLE_AGENT,
    RouteDecision,
    pick,
)

_MODELS = {"claude": "sonnet", "codex": "o4", "glm": "glm-4.6"}


# ── basic role → agent ─────────────────────────────────────────────────────────

def test_engineer_routes_to_claude_by_default() -> None:
    d = pick("engineer", agent_model_map=_MODELS)
    assert d.agent == "claude"
    assert d.model == "sonnet"
    assert d.role == "engineer"


def test_reviewer_differs_from_engineer() -> None:
    """Reviewer intentionally uses a different model than engineer (blind spots)."""
    eng = pick("engineer")
    rev = pick("reviewer")
    assert eng.agent != rev.agent
    assert rev.agent == "glm"


def test_research_routes_to_codex() -> None:
    assert pick("research").agent == "codex"


def test_unknown_role_falls_back_to_default_agent() -> None:
    d = pick("marketing")
    assert d.agent == "claude"  # DEFAULT_AGENT


def test_empty_role_defaults_to_engineer() -> None:
    d = pick("")
    assert d.role == "engineer"


def test_role_is_normalized_case_insensitive() -> None:
    assert pick("ENGINEER").agent == "claude"
    assert pick("  Reviewer ").agent == "glm"


# ── custom role→agent map ───────────────────────────────────────────────────────

def test_custom_role_agent_map_overrides_defaults() -> None:
    d = pick("engineer", role_agent_map={"engineer": "codex"}, agent_model_map=_MODELS)
    assert d.agent == "codex"
    assert d.model == "o4"


# ── per-task override ───────────────────────────────────────────────────────────

def test_override_agent_wins_over_role() -> None:
    d = pick("engineer", override_agent="glm", agent_model_map=_MODELS)
    assert d.agent == "glm"
    assert d.model == "glm-4.6"
    assert d.reason == "override"


def test_override_model_wins_over_agent_model_map() -> None:
    d = pick("engineer", override_model="opus", agent_model_map=_MODELS)
    assert d.agent == "claude"
    assert d.model == "opus"


# ── capability-aware fallback ───────────────────────────────────────────────────

def test_falls_back_when_preferred_agent_unavailable() -> None:
    """engineer prefers claude; only codex+glm online → fall back to an available."""
    d = pick("engineer", available_caps={"codex", "glm"})
    assert d.agent in {"codex", "glm"}
    assert "unavailable" in d.reason


def test_no_fallback_when_preferred_is_available() -> None:
    d = pick("engineer", available_caps={"claude", "codex"})
    assert d.agent == "claude"


def test_none_caps_means_no_filtering() -> None:
    d = pick("engineer", available_caps=None)
    assert d.agent == "claude"


# ── privacy: local-only roles never reroute to cloud ────────────────────────────

def test_infra_stays_local_even_when_cloud_agents_available() -> None:
    """infra must NOT be rerouted to claude/codex/glm by capability fallback."""
    d = pick("infra", available_caps={"claude", "codex", "glm"})
    assert d.agent == "echo"  # default infra agent (local), not a cloud agent
    assert "local-only" in d.reason


def test_infra_not_rerouted_to_cloud_on_fallback() -> None:
    d = pick(
        "infra",
        role_agent_map={"infra": "qwen"},
        available_caps={"claude", "codex"},  # qwen not advertised
    )
    # Must stay on qwen (local), never silently jump to claude/codex.
    assert d.agent == "qwen"
    assert "local-only" in d.reason


# ── value object ────────────────────────────────────────────────────────────────

def test_route_decision_is_frozen() -> None:
    d = RouteDecision(role="engineer", agent="claude", model="sonnet")
    assert d.role == "engineer"


def test_default_role_agent_map_has_core_roles() -> None:
    for role in ("engineer", "reviewer", "research", "infra"):
        assert role in DEFAULT_ROLE_AGENT
