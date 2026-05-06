"""User agent config repository (per-user enabled/role/model).

Pengganti env var ENABLE_CODEX/CLAUDE/GLM + AGENT_ROLE_*. Setiap user punya
row sendiri per agent_id, di-manage via Telegram & TUI commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.adapters.database.models import UserAgentConfigModel

# Agent yang dikenal dan default mapping role.
KNOWN_AGENTS: tuple[str, ...] = ("codex", "claude", "glm")
DEFAULT_ROLE: dict[str, str] = {
    "codex":  "engineer",
    "claude": "reviewer",
    "glm":    "architect",
}
VALID_ROLES: tuple[str, ...] = ("engineer", "reviewer", "architect")


@dataclass(frozen=True)
class AgentConfig:
    user_id: str
    agent_id: str
    enabled: bool
    role: str | None
    model: str | None
    concurrency: int = 1


class UserAgentConfigRepository:
    def __init__(self, factory: sessionmaker[Any]) -> None:
        self._factory = factory

    def list(self, user_id: str) -> list[AgentConfig]:
        with self._factory() as session:
            rows = list(session.scalars(
                select(UserAgentConfigModel)
                .where(UserAgentConfigModel.user_id == user_id)
            ))
            return [
                AgentConfig(
                    user_id=r.user_id,
                    agent_id=r.agent_id,
                    enabled=r.enabled,
                    role=r.role,
                    model=r.model,
                )
                for r in rows
            ]

    def get(self, user_id: str, agent_id: str) -> AgentConfig | None:
        with self._factory() as session:
            row = session.scalar(
                select(UserAgentConfigModel).where(
                    UserAgentConfigModel.user_id == user_id,
                    UserAgentConfigModel.agent_id == agent_id,
                )
            )
            if row is None:
                return None
            return AgentConfig(
                user_id=row.user_id,
                agent_id=row.agent_id,
                enabled=row.enabled,
                role=row.role,
                model=row.model,
                concurrency=row.concurrency,
            )

    def upsert(
        self,
        user_id: str,
        agent_id: str,
        *,
        enabled: bool | None = None,
        role: str | None = None,
        model: str | None = None,
    ) -> AgentConfig:
        """Create-or-update — None param berarti pertahankan existing."""
        with self._factory() as session:
            row = session.scalar(
                select(UserAgentConfigModel).where(
                    UserAgentConfigModel.user_id == user_id,
                    UserAgentConfigModel.agent_id == agent_id,
                )
            )
            if row is None:
                row = UserAgentConfigModel(
                    user_id=user_id,
                    agent_id=agent_id,
                    enabled=bool(enabled) if enabled is not None else False,
                    role=role if role is not None else DEFAULT_ROLE.get(agent_id),
                    model=model,
                )
                session.add(row)
            else:
                if enabled is not None:
                    row.enabled = enabled
                if role is not None:
                    row.role = role
                if model is not None:
                    row.model = model
            session.commit()
            return AgentConfig(
                user_id=row.user_id,
                agent_id=row.agent_id,
                enabled=row.enabled,
                role=row.role,
                model=row.model,
                concurrency=row.concurrency,
            )

    def agent_for_role(self, user_id: str, role: str) -> str | None:
        """Cari agent yang enabled + assigned ke role tertentu untuk user."""
        with self._factory() as session:
            row = session.scalar(
                select(UserAgentConfigModel).where(
                    UserAgentConfigModel.user_id == user_id,
                    UserAgentConfigModel.role == role,
                    UserAgentConfigModel.enabled.is_(True),
                )
            )
            return row.agent_id if row else None
