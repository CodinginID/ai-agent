"""Port untuk persisten chat history per user.

Implementasi konkret bisa in-memory (dev/test), Postgres (production), atau
Redis (kalau perlu).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    created_at: datetime


class ChatHistoryStore(Protocol):
    def append(self, user_id: str, role: Role, content: str) -> None: ...

    def recent(self, user_id: str, limit: int) -> list[ChatMessage]: ...

    def clear(self, user_id: str) -> None: ...
