"""Domain entity untuk pesan + event yang dipancarkan use case.

Setiap interaksi user (Telegram message, TUI input, atau HTTP /chat/send)
diwakili oleh ``MessageContext``. Use case yield rangkaian ``ChatEvent`` yang
adapter (Telegram/HTTP/TUI) terjemahkan ke output mereka masing-masing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ChatEventType(str, Enum):
    THINKING = "thinking"
    INTENT_CLASSIFIED = "intent_classified"
    APPROVAL_REQUIRED = "approval_required"
    ACTION_STARTED = "action_started"
    ACTION_RESULT = "action_result"
    TEXT_CHUNK = "text_chunk"
    FINAL = "final"
    ERROR = "error"
    # Use case yield event ini saat intent agent_* — handler luar (chat.py SSE
    # / bot.py handle_text) yang ngeksekusi via worker tunnel.
    DELEGATE_TO_AGENT = "delegate_to_agent"
    # Execution loop events — emitted by ExecutionLoop for complex requests.
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    RETRYING = "retrying"


@dataclass(frozen=True)
class MessageContext:
    """Konteks pesan dari user — independen dari medium (Telegram/TUI/HTTP)."""

    user_id: str  # UUID user dari DB
    conversation_id: str  # Telegram chat_id (str), atau session id TUI
    project_id: str
    project_root: Path
    project_name: str
    telegram_user_id: int | None = None  # untuk audit, optional
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatEvent:
    """Event yang dipancarkan use case selama proses pesan."""

    type: ChatEventType
    payload: dict[str, Any]

    @classmethod
    def thinking(cls, message: str) -> ChatEvent:
        return cls(ChatEventType.THINKING, {"message": message})

    @classmethod
    def intent_classified(cls, intent: str, confidence: float, reason: str) -> ChatEvent:
        return cls(
            ChatEventType.INTENT_CLASSIFIED,
            {"intent": intent, "confidence": confidence, "reason": reason},
        )

    @classmethod
    def approval_required(cls, plan_id: str, summary: str) -> ChatEvent:
        return cls(
            ChatEventType.APPROVAL_REQUIRED,
            {"plan_id": plan_id, "summary": summary},
        )

    @classmethod
    def action_started(cls, action: str) -> ChatEvent:
        return cls(ChatEventType.ACTION_STARTED, {"action": action})

    @classmethod
    def action_result(cls, action: str, output: str) -> ChatEvent:
        return cls(ChatEventType.ACTION_RESULT, {"action": action, "output": output})

    @classmethod
    def text_chunk(cls, text: str) -> ChatEvent:
        return cls(ChatEventType.TEXT_CHUNK, {"text": text})

    @classmethod
    def final(cls, text: str) -> ChatEvent:
        return cls(ChatEventType.FINAL, {"text": text})

    @classmethod
    def error(cls, message: str) -> ChatEvent:
        return cls(ChatEventType.ERROR, {"message": message})

    @classmethod
    def delegate_to_agent(
        cls,
        agent: str,
        prompt: str,
        intent: str,
        role: str = "",
    ) -> ChatEvent:
        return cls(
            ChatEventType.DELEGATE_TO_AGENT,
            {"agent": agent, "prompt": prompt, "intent": intent, "role": role},
        )

    @classmethod
    def observing(cls, message: str) -> ChatEvent:
        return cls(ChatEventType.OBSERVING, {"message": message})

    @classmethod
    def reflecting(cls, message: str) -> ChatEvent:
        return cls(ChatEventType.REFLECTING, {"message": message})

    @classmethod
    def retrying(cls, attempt: int, reason: str) -> ChatEvent:
        return cls(ChatEventType.RETRYING, {"attempt": attempt, "reason": reason})
