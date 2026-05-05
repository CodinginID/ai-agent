"""ChatHistoryStore implementations.

Dua varian:
- ``InMemoryChatHistory`` — untuk test atau dev offline.
- ``SqlAlchemyChatHistory`` — DB-backed via SQLAlchemy session factory.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.adapters.database.models import ChatMessageModel
from app.ports.chat_history import ChatHistoryStore, ChatMessage, Role


class InMemoryChatHistory(ChatHistoryStore):
    """Per-process memory store. Hilang saat restart."""

    def __init__(self) -> None:
        self._by_user: dict[str, list[ChatMessage]] = defaultdict(list)

    def append(self, user_id: str, role: Role, content: str) -> None:
        self._by_user[user_id].append(
            ChatMessage(role=role, content=content, created_at=datetime.now(UTC))
        )

    def recent(self, user_id: str, limit: int) -> list[ChatMessage]:
        return list(self._by_user[user_id][-limit:])

    def clear(self, user_id: str) -> None:
        self._by_user.pop(user_id, None)


class SqlAlchemyChatHistory(ChatHistoryStore):
    """DB-backed history. Pakai conversation_id "default" sementara — multi-conv
    bisa ditambah belakangan tanpa schema change."""

    _DEFAULT_CONV = "default"

    def __init__(self, session_factory: sessionmaker[Any]) -> None:
        self._factory = session_factory

    def append(self, user_id: str, role: Role, content: str) -> None:
        with self._factory() as session:
            session.add(ChatMessageModel(
                user_id=user_id,
                conversation_id=self._DEFAULT_CONV,
                role=role,
                content=content,
            ))
            session.commit()

    def recent(self, user_id: str, limit: int) -> list[ChatMessage]:
        with self._factory() as session:
            rows = list(session.scalars(
                select(ChatMessageModel)
                .where(ChatMessageModel.user_id == user_id)
                .order_by(ChatMessageModel.created_at.desc())
                .limit(limit)
            ))
        # Reverse supaya ascending (terlama → terbaru)
        return [
            ChatMessage(role=r.role, content=r.content, created_at=r.created_at)  # type: ignore[arg-type]
            for r in reversed(rows)
        ]

    def clear(self, user_id: str) -> None:
        with self._factory() as session:
            session.query(ChatMessageModel).filter(
                ChatMessageModel.user_id == user_id
            ).delete()
            session.commit()
