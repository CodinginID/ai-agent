"""Port for the Project Manager Agent.

Defines the Protocol that any planning agent implementation must satisfy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.agents.pm import TaskPlan


class PMAgentPort(Protocol):
    def plan(self, request: str, context: str = "") -> TaskPlan: ...
