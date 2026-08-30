"""Port for the Project Manager Agent.

Defines the Protocol that any planning agent implementation must satisfy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.agents.pm import TaskPlan
    from app.ports.ai_provider import AIProvider


class PMAgentPort(Protocol):
    def plan(
        self, request: str, context: str = "", provider: AIProvider | None = None
    ) -> TaskPlan: ...

    def build_prompt(self, request: str, context: str = "") -> str: ...

    def parse(self, response: str) -> TaskPlan: ...
