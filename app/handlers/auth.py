from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.database.repositories import ControlPlaneRepository
from app.adapters.database.session import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker
    from telegram import Update

_db_session_factory: sessionmaker[Session] | None = None


def get_db_session_factory() -> sessionmaker[Session]:
    global _db_session_factory
    if _db_session_factory is None:
        _db_session_factory = create_session_factory(
            create_database_engine(settings.database_url)
        )
    return _db_session_factory


def is_authorized(update: Update) -> bool:
    if settings.allow_unrestricted_access:
        return True

    user = update.effective_user
    return bool(user and user.id in settings.admin_user_ids)


async def deny_if_unauthorized(update: Update) -> bool:
    if is_authorized(update):
        return False

    await update.message.reply_text(  # type: ignore[union-attr]
        "Akses ditolak. Kirim /whoami untuk melihat Telegram user ID, "
        "lalu masukkan ID itu ke ADMIN_USER_IDS di .env."
    )
    return True


def resolve_user_id_from_telegram(telegram_user_id: int | None) -> str | None:
    """Lookup user_id (UUID) berdasarkan telegram_user_id."""
    if telegram_user_id is None:
        return None

    try:
        with session_scope(get_db_session_factory()) as session:
            repo = ControlPlaneRepository(session)
            tenant = repo.resolve_by_telegram_user_id(telegram_user_id)
            return tenant.user_id if tenant else None
    except Exception:
        return None
