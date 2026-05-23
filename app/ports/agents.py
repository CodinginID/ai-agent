from collections.abc import Sequence
from typing import Protocol

from app.domain.agents import AgentCapability


class AgentDiscoveryPort(Protocol):
    def discover(self) -> Sequence[AgentCapability]: ...


class AgentRoleResolver(Protocol):
    """Resolve (user_id, role) → agent CLI name from persistent config."""

    def agent_for_role(self, user_id: str, role: str) -> str | None: ...


class HandoffContextProvider(Protocol):
    """Prepend the prior role's last output to the current prompt, if any."""

    def prepend_context(self, project_id: str, role: str, prompt: str) -> str: ...
