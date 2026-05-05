from collections.abc import Sequence
from typing import Protocol

from app.domain.agents import AgentCapability


class AgentDiscoveryPort(Protocol):
    def discover(self) -> Sequence[AgentCapability]: ...
