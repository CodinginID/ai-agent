"""SqlAgentRoleResolver — resolve (user_id, role) → agent CLI name via DB."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.agent_configs import UserAgentConfigRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


@dataclass
class SqlAgentRoleResolver:
    _factory: sessionmaker[Any]

    def agent_for_role(self, user_id: str, role: str) -> str | None:
        return UserAgentConfigRepository(self._factory).agent_for_role(user_id, role)
