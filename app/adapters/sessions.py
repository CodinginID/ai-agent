"""User session repository.

Token opaque (random URL-safe string) dikembalikan ke klien, tapi yang disimpan
di DB adalah **hash SHA-256**-nya — kalau DB bocor, token asli tidak ikut bocor.
Lookup (resolve/revoke) meng-hash token yang masuk lalu mencocokkan. Validasi
kedaluwarsa pakai `expires_at`.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

from app.adapters.database.models import UserSessionModel

_TOKEN_BYTES = 32  # ~43 chars URL-safe base64
DEFAULT_TTL = timedelta(days=30)


def _hash_token(token: str) -> str:
    """SHA-256 hex (64 char) — muat persis di kolom token String(64)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
                token=_hash_token(token),  # simpan hash, bukan token asli
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
        hashed = _hash_token(token)
        with self._factory() as session:
            row = session.scalar(
                select(UserSessionModel).where(UserSessionModel.token == hashed)
            )
            if row is None:
                return None
            if _ensure_utc(row.expires_at) <= now:
                return None
            row.last_used_at = now
            session.commit()
            return SessionInfo(
                user_id=row.user_id,
                token=token,  # kembalikan token asli yang dikirim caller
                expires_at=_ensure_utc(row.expires_at),
            )

    def revoke(self, token: str) -> bool:
        with self._factory() as session:
            result = session.execute(
                delete(UserSessionModel).where(UserSessionModel.token == _hash_token(token))
            )
            session.commit()
            return bool(result.rowcount > 0)

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
