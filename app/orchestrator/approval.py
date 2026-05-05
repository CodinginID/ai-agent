from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.intents.schemas import ExecutionPlan

_DEFAULT_TTL_MINUTES: int = 5


@dataclass
class PendingPlan:
    plan: ExecutionPlan
    chat_id: int
    user_text: str
    action_context: dict[str, Any]
    expires_at: datetime


class PendingPlanStore:
    def __init__(self, ttl_minutes: int = _DEFAULT_TTL_MINUTES) -> None:
        self._plans: dict[str, PendingPlan] = {}
        self._lock = threading.Lock()
        self._ttl = timedelta(minutes=ttl_minutes)

    def save(
        self,
        plan: ExecutionPlan,
        chat_id: int,
        user_text: str,
        action_context: dict[str, Any],
    ) -> None:
        with self._lock:
            self._evict_expired()
            self._plans[plan.plan_id] = PendingPlan(
                plan=plan,
                chat_id=chat_id,
                user_text=user_text,
                action_context=action_context,
                expires_at=datetime.now() + self._ttl,
            )

    def consume(self, plan_id: str, chat_id: int) -> PendingPlan | None:
        """Remove and return plan if it belongs to chat_id and has not expired."""
        with self._lock:
            pending = self._plans.pop(plan_id, None)
            if pending is None:
                return None
            if pending.chat_id != chat_id:
                self._plans[plan_id] = pending  # put back — wrong chat
                return None
            if datetime.now() > pending.expires_at:
                return None
            return pending

    def cancel(self, plan_id: str, chat_id: int) -> bool:
        with self._lock:
            pending = self._plans.get(plan_id)
            if pending is None or pending.chat_id != chat_id:
                return False
            del self._plans[plan_id]
            return True

    def list_for_chat(self, chat_id: int) -> list[PendingPlan]:
        with self._lock:
            self._evict_expired()
            return [p for p in self._plans.values() if p.chat_id == chat_id]

    def _evict_expired(self) -> None:
        now = datetime.now()
        expired = [k for k, v in self._plans.items() if now > v.expires_at]
        for k in expired:
            del self._plans[k]
