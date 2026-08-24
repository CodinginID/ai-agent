import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.domain.agents import AgentCapability

ExecutableFinder = Callable[[str], str | None]


@dataclass(frozen=True)
class CliAgentDefinition:
    agent_id: str
    display_name: str
    provider: str
    role_hint: str
    executable: str
    enabled: bool
    model: str | None = None
    access_mode: str | None = None
    description: str = ""


class CliAgentDiscoveryAdapter:
    def __init__(
        self,
        definitions: Sequence[CliAgentDefinition],
        executable_finder: ExecutableFinder | None = None,
    ) -> None:
        self._definitions = tuple(definitions)
        self._executable_finder = executable_finder or shutil.which

    def discover(self) -> tuple[AgentCapability, ...]:
        capabilities: list[AgentCapability] = []

        for definition in self._definitions:
            path = self._executable_finder(definition.executable)
            capabilities.append(
                AgentCapability(
                    agent_id=definition.agent_id,
                    display_name=definition.display_name,
                    provider=definition.provider,
                    role_hint=definition.role_hint,
                    enabled=definition.enabled,
                    available=path is not None,
                    executable=definition.executable,
                    path=path,
                    model=definition.model,
                    access_mode=definition.access_mode,
                    description=definition.description,
                )
            )

        return tuple(capabilities)
