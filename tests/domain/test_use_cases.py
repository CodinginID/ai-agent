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


def test_audit_emits_request_intent_and_response_events() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    resolver = MagicMock()
    resolver.agent_for_role.return_value = "codex"

    audit = MagicMock()
    uc = _make_use_case(
        intent_parser=intent_parser,
        agent_resolver=resolver,
        audit=audit,
    )

    list(uc.handle("refactor kode X", _make_ctx()))

    event_names = [call.args[0] for call in audit.log.call_args_list]
    assert "request_received" in event_names
    assert "intent_parsed" in event_names
    assert "response_sent" in event_names
    # response_sent harus event terakhir supaya trace tertutup rapi.
    assert event_names[-1] == "response_sent"


def test_audit_propagates_trace_id_from_context() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    resolver = MagicMock()
    resolver.agent_for_role.return_value = "codex"

    audit = MagicMock()
    ctx = MessageContext(
        user_id="u1",
        conversation_id="chat-1",
        project_id="p1",
        project_root=Path("/workspace"),
        project_name="test-project",
        trace_id="fixed-trace-uuid",
    )

    uc = _make_use_case(
        intent_parser=intent_parser,
        agent_resolver=resolver,
        audit=audit,
    )
    list(uc.handle("refactor", ctx))

    for call in audit.log.call_args_list:
        assert call.args[1] == "fixed-trace-uuid"


def test_audit_emits_error_event_on_intent_parse_failure() -> None:
    from app.domain.exceptions import IntentParseError

    intent_parser = MagicMock()
    intent_parser.parse.side_effect = IntentParseError("bad json")

    audit = MagicMock()
    uc = _make_use_case(intent_parser=intent_parser, audit=audit)

    list(uc.handle("apa kabar", _make_ctx()))

    event_names = [call.args[0] for call in audit.log.call_args_list]
    assert "error" in event_names
    assert event_names[-1] == "response_sent"
    # response_sent should mark error outcome
    last_call = audit.log.call_args_list[-1]
    assert last_call.kwargs.get("outcome") == "error"


def test_audit_is_optional_use_case_runs_without_logger() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    resolver = MagicMock()
    resolver.agent_for_role.return_value = "codex"

    uc = _make_use_case(intent_parser=intent_parser, agent_resolver=resolver, audit=None)
    events = list(uc.handle("refactor", _make_ctx()))

    assert events  # use case still produces events with no logger


def test_message_context_generates_unique_trace_id_by_default() -> None:
    ctx_a = MessageContext(
        user_id="u",
        conversation_id="c",
        project_id="p",
        project_root=Path("/x"),
        project_name="x",
    )
    ctx_b = MessageContext(
        user_id="u",
        conversation_id="c",
        project_id="p",
        project_root=Path("/x"),
        project_name="x",
    )
    assert ctx_a.trace_id != ctx_b.trace_id
    assert len(ctx_a.trace_id) >= 32  # uuid4 length


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
