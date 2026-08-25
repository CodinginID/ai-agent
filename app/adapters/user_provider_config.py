# app/adapters/user_provider_config.py
"""Repository preferensi provider per-user."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.database.models import UserProviderConfigModel

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


class UserProviderConfigRepository:
    def __init__(self, factory: sessionmaker[Any]) -> None:
        self._factory = factory

    def get(self, user_id: str) -> tuple[str, str | None] | None:
        with self._factory() as session:
            row = session.get(UserProviderConfigModel, user_id)
            return (row.provider, row.model) if row else None

    def set(self, user_id: str, provider: str, model: str | None = None) -> None:
        with self._factory() as session:
            row = session.get(UserProviderConfigModel, user_id)
            if row is None:
                session.add(
                    UserProviderConfigModel(
                        user_id=user_id, provider=provider, model=model
                    )
                )
            else:
                row.provider = provider
                row.model = model
            session.commit()
