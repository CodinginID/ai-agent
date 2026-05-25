"""Unit tests HandleMessageUseCase — domain layer, zero adapter imports."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from app.domain.messaging import MessageContext
from app.domain.use_cases import HandleMessageUseCase
from app.intents.schemas import Intent


def _make_ctx(user_id: str = "u1", project_id: str = "p1") -> MessageContext:
    return MessageContext(
        user_id=user_id,
        conversation_id="chat-1",
        project_id=project_id,
        project_root=Path("/workspace"),
        project_name="test-project",
    )


def _make_intent(intent: str = "agent_code", confidence: float = 0.95) -> Intent:
    return Intent(
        intent=intent,
        project_id="p1",
        confidence=confidence,
        requires_approval=False,
        parameters={},
        reason="test",
    )


def _make_use_case(**overrides: Any) -> HandleMessageUseCase:
    defaults: dict[str, Any] = {
        "ai": MagicMock(),
        "intent_parser": MagicMock(),
        "plan_generator": MagicMock(),
        "action_registry": MagicMock(),
        "pending_plans": MagicMock(),
        "history": MagicMock(),
    }
    defaults.update(overrides)
    return HandleMessageUseCase(**defaults)


def test_agent_delegation_yields_error_when_no_resolver() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    uc = _make_use_case(intent_parser=intent_parser, agent_resolver=None)
    events = list(uc.handle("refactor kode X", _make_ctx()))

    types = [e.type for e in events]
    assert "error" in types


def test_agent_delegation_yields_error_when_no_agent_configured() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    resolver = MagicMock()
    resolver.agent_for_role.return_value = None

    uc = _make_use_case(intent_parser=intent_parser, agent_resolver=resolver)
    events = list(uc.handle("refactor kode X", _make_ctx()))

    types = [e.type for e in events]
    assert "error" in types


def test_agent_delegation_yields_delegate_event() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    resolver = MagicMock()
    resolver.agent_for_role.return_value = "codex"

    uc = _make_use_case(intent_parser=intent_parser, agent_resolver=resolver)
    events = list(uc.handle("refactor kode X", _make_ctx()))

    types = [e.type for e in events]
    assert "delegate_to_agent" in types


def test_rate_limited_user_gets_error_event() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    limiter = MagicMock()
    limiter.is_allowed.return_value = False

    uc = _make_use_case(intent_parser=intent_parser, rate_limiter=limiter)
    events = list(uc.handle("apapun", _make_ctx()))

    types = [e.type for e in events]
    assert types == ["error"]
    assert "tunggu sebentar" in events[0].payload["message"].lower()
    intent_parser.parse.assert_not_called()
    assert "intent_classified" not in types


def test_rate_limiter_allowed_lets_classification_proceed() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    limiter = MagicMock()
    limiter.is_allowed.return_value = True

    resolver = MagicMock()
    resolver.agent_for_role.return_value = "codex"

    uc = _make_use_case(
        intent_parser=intent_parser,
        rate_limiter=limiter,
        agent_resolver=resolver,
    )
    events = list(uc.handle("refactor kode X", _make_ctx()))

    types = [e.type for e in events]
    assert "intent_classified" in types
    limiter.is_allowed.assert_called_once_with("u1")


def test_agent_delegation_uses_handoff_provider_when_present() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_review")

    resolver = MagicMock()
    resolver.agent_for_role.return_value = "claude"

    handoff = MagicMock()
    handoff.prepend_context.return_value = "[HANDOFF]\nreview kode X"

    uc = _make_use_case(
        intent_parser=intent_parser,
        agent_resolver=resolver,
        handoff_provider=handoff,
    )
    events = list(uc.handle("review kode X", _make_ctx()))

    handoff.prepend_context.assert_called_once()
    delegate_events = [e for e in events if e.type == "delegate_to_agent"]
    assert delegate_events
    assert "[HANDOFF]" in delegate_events[0].payload["prompt"]
