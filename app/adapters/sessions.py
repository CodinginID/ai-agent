"""User session repository.

Token opaque (random URL-safe string), disimpan plain di DB karena tidak ada
risiko offline-attack untuk single-user-per-token. Validasi pakai `expires_at`.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app.adapters.database.models import UserSessionModel

_TOKEN_BYTES = 32  # ~43 chars URL-safe base64
DEFAULT_TTL = timedelta(days=30)


def _ensure_utc(dt: datetime) -> datetime:
    """SQLite buang tzinfo saat read; assume UTC supaya konsisten dengan Postgres."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


@dataclass(frozen=True)
class SessionInfo:
    user_id: str
    token: str
    expires_at: datetime


class UserSessionRepository:
    def __init__(self, factory: sessionmaker[Any]) -> None:
        self._factory = factory

    def create(
        self,
        user_id: str,
        ttl: timedelta = DEFAULT_TTL,
        user_agent: str | None = None,
    ) -> SessionInfo:
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        now = datetime.now(UTC)
        expires_at = now + ttl

        with self._factory() as session:
            row = UserSessionModel(
                user_id=user_id,
                token=token,
                created_at=now,
                expires_at=expires_at,
                last_used_at=now,
                user_agent=user_agent,
            )
            session.add(row)
            session.commit()

        return SessionInfo(user_id=user_id, token=token, expires_at=expires_at)

    def resolve(self, token: str) -> SessionInfo | None:
        if not token:
            return None
        now = datetime.now(UTC)
        with self._factory() as session:
            row = session.scalar(
                select(UserSessionModel).where(UserSessionModel.token == token)
            )
            if row is None:
                return None
            if _ensure_utc(row.expires_at) <= now:
                return None
            row.last_used_at = now
            session.commit()
            return SessionInfo(
                user_id=row.user_id,
                token=row.token,
                expires_at=_ensure_utc(row.expires_at),
            )

    def revoke(self, token: str) -> bool:
        with self._factory() as session:
            result = session.execute(
                delete(UserSessionModel).where(UserSessionModel.token == token)
            )
            session.commit()
            return result.rowcount > 0

    def revoke_all_for_user(self, user_id: str) -> int:
        with self._factory() as session:
            result = session.execute(
                delete(UserSessionModel).where(UserSessionModel.user_id == user_id)
            )
            session.commit()
            return result.rowcount or 0

    def purge_expired(self) -> int:
        now = datetime.now(UTC)
        with self._factory() as session:
            result = session.execute(
                delete(UserSessionModel).where(UserSessionModel.expires_at <= now)
            )
            session.commit()
            return result.rowcount or 0
