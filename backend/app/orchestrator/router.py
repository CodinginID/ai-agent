"""Role → (agent, model) router for worker delegation.

The orchestrator decides *what kind* of work a step is (a ``role``); this module
turns that role into a concrete ``(agent, model)`` pair to dispatch to a worker.

Pure & deterministic — no I/O, no globals. Maps are passed in so the caller
(composition / adapter) owns config sourcing and this stays trivially testable.

Design pillars (see docs/ORCHESTRATOR.md):
- Each role can map to a different agent/LLM → "every worker a different model".
- ``reviewer`` should differ from ``engineer`` on purpose (catch blind spots).
- ``infra`` is privacy-sensitive: it must resolve to a local agent and is never
  silently rerouted to a cloud agent by capability fallback.
- Capability-aware: if the user's workers don't have the preferred agent's CLI
  installed, fall back to an available one — except for ``infra`` (privacy).
- Per-task override always wins (explicit user/orchestrator intent).
"""

from __future__ import annotations

from dataclasses import dataclass

# Roles whose work must stay on a local agent — never rerouted to cloud agents
# by capability fallback. Server ops / sensitive context must not leave the box.
LOCAL_ONLY_ROLES: frozenset[str] = frozenset({"infra"})

# Agents considered local (run on the user's own machine without sending the
# task to a third-party cloud model). ``echo`` is the safe local no-op default.
LOCAL_AGENTS: frozenset[str] = frozenset({"echo", "local", "qwen"})

DEFAULT_ROLE_AGENT: dict[str, str] = {
    "engineer": "claude",
    "reviewer": "glm",
    "research": "codex",
    "infra": "echo",
}

DEFAULT_AGENT = "claude"


@dataclass(frozen=True)
class RouteDecision:
    role: str
    agent: str
    model: str
    reason: str = ""


def pick(
    role: str,
    *,
    role_agent_map: dict[str, str] | None = None,
    agent_model_map: dict[str, str] | None = None,
    available_caps: frozenset[str] | set[str] | None = None,
    override_agent: str = "",
    override_model: str = "",
) -> RouteDecision:
    """Resolve a role into a concrete ``(agent, model)`` dispatch decision.

    Args:
        role: logical role (engineer/reviewer/research/infra/...).
        role_agent_map: role → agent name. Defaults to ``DEFAULT_ROLE_AGENT``.
        agent_model_map: agent → model string (e.g. {"claude": "sonnet"}).
            Empty/absent model means "let the agent CLI use its own default".
        available_caps: agent names that at least one online worker can run.
            ``None`` means "unknown" → no capability filtering applied.
        override_agent: explicit agent, wins over role mapping.
        override_model: explicit model, wins over agent_model_map.

    Returns:
        RouteDecision with the chosen agent + model + a human-readable reason.
    """
    role_agent_map = role_agent_map or DEFAULT_ROLE_AGENT
    agent_model_map = agent_model_map or {}
    role_norm = (role or "").strip().lower() or "engineer"

    # 1. Explicit override always wins.
    if override_agent:
        agent = override_agent.strip().lower()
        model = override_model or agent_model_map.get(agent, "")
        return RouteDecision(role_norm, agent, model, reason="override")

    # 2. Role → preferred agent.
    preferred = role_agent_map.get(role_norm, DEFAULT_AGENT)

    # 3. Capability-aware fallback (skipped for local-only roles).
    agent = preferred
    reason = f"role '{role_norm}' → {preferred}"
    if available_caps is not None and preferred not in available_caps:
        if role_norm in LOCAL_ONLY_ROLES:
            # Privacy: never reroute infra to a cloud agent. Keep preferred even
            # if no worker advertises it — caller surfaces "no worker" cleanly.
            reason = f"local-only role '{role_norm}' pinned to {preferred} (no fallback)"
        else:
            fallback = _first_available(role_agent_map, available_caps)
            if fallback:
                agent = fallback
                reason = f"role '{role_norm}' preferred {preferred} unavailable → {fallback}"
            else:
                reason = f"role '{role_norm}' → {preferred} (no caps advertised, best-effort)"

    model = override_model or agent_model_map.get(agent, "")
    return RouteDecision(role_norm, agent, model, reason=reason)


def _first_available(
    role_agent_map: dict[str, str],
    available_caps: frozenset[str] | set[str],
) -> str:
    """Pick a deterministic available agent: prefer ones referenced by the map,
    excluding local-only placeholders, then any advertised cap."""
    # Prefer agents that some role maps to (stable, meaningful choices).
    for agent in dict.fromkeys(role_agent_map.values()):
        if agent in available_caps and agent not in LOCAL_AGENTS:
            return agent
    # Otherwise any advertised cloud-capable cap (sorted for determinism).
    for agent in sorted(available_caps):
        if agent not in LOCAL_AGENTS:
            return agent
    return ""
