from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentCapability:
    agent_id: str
    display_name: str
    provider: str
    role_hint: str
    enabled: bool
    available: bool
    executable: str | None = None
    path: str | None = None
    model: str | None = None
    access_mode: str | None = None
    description: str = ""

    @property
    def ready(self) -> bool:
        return self.enabled and self.available

    @property
    def status(self) -> str:
        if self.ready:
            return "ready"
        if self.available:
            return "installed_disabled"
        if self.enabled:
            return "enabled_missing"
        return "disabled_missing"


@dataclass(frozen=True)
class AgentRoleAssignment:
    role: str
    agent_id: str
    ready: bool
    status: str
    detail: str


def resolve_agent_roles(
    capabilities: Sequence[AgentCapability],
    assignments: Mapping[str, str],
) -> tuple[AgentRoleAssignment, ...]:
    capabilities_by_id = {capability.agent_id: capability for capability in capabilities}
    resolved: list[AgentRoleAssignment] = []

    for role, agent_id in assignments.items():
        capability = capabilities_by_id.get(agent_id)
        if capability is None:
            resolved.append(
                AgentRoleAssignment(
                    role=role,
                    agent_id=agent_id,
                    ready=False,
                    status="unknown_agent",
                    detail="agent is not registered",
                )
            )
            continue

        resolved.append(
            AgentRoleAssignment(
                role=role,
                agent_id=agent_id,
                ready=capability.ready,
                status=capability.status,
                detail=agent_status_detail(capability),
            )
        )

    return tuple(resolved)


def agent_status_detail(capability: AgentCapability) -> str:
    if capability.ready:
        return "enabled and available"
    if capability.available:
        return "installed on server but disabled in configuration"
    if capability.enabled:
        return "enabled in configuration but executable is missing"
    return "disabled in configuration and executable is missing"


def readiness_message(assignments: Sequence[AgentRoleAssignment]) -> str:
    """Return a human-readable summary of assigned agents' readiness."""
    if not assignments:
        return "No agents assigned."
    ready = [a for a in assignments if a.ready]
    not_ready = [a for a in assignments if not a.ready]
    parts: list[str] = []
    if ready:
        parts.append(f"{len(ready)} agent(s) ready: " + ", ".join(a.agent_id for a in ready))
    if not_ready:
        parts.append(f"{len(not_ready)} not ready: " + ", ".join(a.agent_id for a in not_ready))
    return ". ".join(parts) + "."
