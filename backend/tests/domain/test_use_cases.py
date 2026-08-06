"""Unit tests HandleMessageUseCase — domain layer, zero adapter imports."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from app.domain.exceptions import (
    ActionExecutionError,
    AIProviderError,
    IntentParseError,
)
from app.domain.messaging import ChatEventType, MessageContext
from app.domain.use_cases import HandleMessageUseCase
from app.intents.schemas import ExecutionPlan, Intent, PlanStep


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
    # Set up parse_with to delegate to parse for backward compatibility with existing tests
    parser = defaults["intent_parser"]
    parser.parse_with.side_effect = lambda caller, text, project_id: parser.parse(text, project_id)
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


# ── Entry-point guard rails ───────────────────────────────────────────────────


def test_empty_text_yields_no_events() -> None:
    uc = _make_use_case()
    events = list(uc.handle("   ", _make_ctx()))
    assert events == []


def test_intent_parse_error_yields_error_event() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.side_effect = IntentParseError("boom")

    uc = _make_use_case(intent_parser=intent_parser)
    events = list(uc.handle("apa kabar", _make_ctx()))

    assert len(events) == 1
    assert events[0].type == ChatEventType.ERROR
    assert "boom" in events[0].payload["message"]


def test_intent_classification_menggunakan_provider_hasil_resolve_per_user() -> None:
    """Regression: verify parse_with receives the resolved provider's chat method."""
    # Set up two distinct AI providers
    default_ai = MagicMock()
    default_ai.chat.return_value = "default response"

    resolved_ai = MagicMock()
    resolved_ai.chat.return_value = "resolved response"

    # Provider resolver returns the resolved AI for user u1
    provider_resolver = MagicMock()
    provider_resolver.for_user.return_value = resolved_ai

    # Intent parser that returns chat intent (simplest path)
    intent_parser = MagicMock()
    intent_parser.parse_with.return_value = _make_intent("chat", confidence=1.0)

    # History mock
    history = MagicMock()
    history.recent.return_value = []

    # Build use case WITHOUT using _make_use_case to avoid the shim
    uc = HandleMessageUseCase(
        ai=default_ai,
        intent_parser=intent_parser,
        plan_generator=MagicMock(),
        action_registry=MagicMock(),
        pending_plans=MagicMock(),
        history=history,
        provider_resolver=provider_resolver,
    )

    # Execute
    list(uc.handle("halo", _make_ctx(user_id="u1")))

    # Verify parse_with was called with the RESOLVED provider's chat method
    assert intent_parser.parse_with.called
    call_args = intent_parser.parse_with.call_args
    caller_arg = call_args[0][0]  # First positional arg is the caller
    text_arg = call_args[0][1]
    project_id_arg = call_args[0][2]

    # The caller should be resolved_ai.chat, NOT default_ai.chat
    assert caller_arg is resolved_ai.chat
    assert text_arg == "halo"
    assert project_id_arg == "p1"

    # Verify the resolver was actually called for the user
    provider_resolver.for_user.assert_called_with("u1")


# ── Chat path ────────────────────────────────────────────────────────────────


def test_chat_intent_streams_chunks_and_final() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("chat", confidence=1.0)

    ai = MagicMock()
    ai.chat_stream.return_value = iter(["hai ", "halo ", "user"])

    history = MagicMock()
    history.recent.return_value = []

    uc = _make_use_case(intent_parser=intent_parser, ai=ai, history=history)
    events = list(uc.handle("halo", _make_ctx()))

    types = [e.type for e in events]
    assert ChatEventType.INTENT_CLASSIFIED in types
    chunk_events = [e for e in events if e.type == ChatEventType.TEXT_CHUNK]
    final_events = [e for e in events if e.type == ChatEventType.FINAL]
    assert [e.payload["text"] for e in chunk_events] == ["hai ", "halo ", "user"]
    assert final_events
    assert final_events[0].payload["text"] == "hai halo user"
    # user + assistant masing-masing satu kali → 2 append
    assert history.append.call_count == 2


def test_chat_intent_skips_empty_chunks() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("chat", confidence=1.0)

    ai = MagicMock()
    ai.chat_stream.return_value = iter(["", "data", ""])

    history = MagicMock()
    history.recent.return_value = []

    uc = _make_use_case(intent_parser=intent_parser, ai=ai, history=history)
    events = list(uc.handle("hi", _make_ctx()))

    chunk_events = [e for e in events if e.type == ChatEventType.TEXT_CHUNK]
    assert [e.payload["text"] for e in chunk_events] == ["data"]


def test_chat_intent_ai_provider_error_yields_error_event() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("chat", confidence=1.0)

    ai = MagicMock()
    ai.chat_stream.side_effect = AIProviderError("network down")

    history = MagicMock()
    history.recent.return_value = []

    uc = _make_use_case(intent_parser=intent_parser, ai=ai, history=history)
    events = list(uc.handle("halo", _make_ctx()))

    error_events = [e for e in events if e.type == ChatEventType.ERROR]
    assert error_events
    assert "network down" in error_events[0].payload["message"]


def test_unknown_intent_routes_to_chat_when_no_execution_loop() -> None:
    """Unknown intent + no execution_loop → still goes through chat path."""
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("unknown", confidence=0.0)

    ai = MagicMock()
    ai.chat_stream.return_value = iter(["maaf"])

    history = MagicMock()
    history.recent.return_value = []

    uc = _make_use_case(intent_parser=intent_parser, ai=ai, history=history)
    events = list(uc.handle("buka kulkas", _make_ctx()))

    final_events = [e for e in events if e.type == ChatEventType.FINAL]
    assert final_events
    assert final_events[0].payload["text"] == "maaf"


# ── Action path (simple, no approval) ─────────────────────────────────────────


def _make_plan(intent: Intent, requires_approval: bool = False) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-1",
        summary="test plan",
        steps=[PlanStep.from_intent(intent)],
        requires_approval=requires_approval,
        project_id=intent.project_id,
        intent=intent.intent,
    )


def test_action_intent_without_approval_yields_started_result_final() -> None:
    intent = _make_intent("memory", confidence=0.95)
    intent_parser = MagicMock()
    intent_parser.parse.return_value = intent

    plan_generator = MagicMock()
    plan_generator.generate.return_value = _make_plan(intent, requires_approval=False)

    action_registry = MagicMock()
    action_registry.execute.return_value = "MemTotal: 16Gi, used: 8Gi"

    ai = MagicMock()
    ai.chat.return_value = "RAM 50% terpakai"

    uc = _make_use_case(
        intent_parser=intent_parser,
        plan_generator=plan_generator,
        action_registry=action_registry,
        ai=ai,
    )
    events = list(uc.handle("cek ram", _make_ctx()))

    types = [e.type for e in events]
    assert ChatEventType.ACTION_STARTED in types
    assert ChatEventType.ACTION_RESULT in types
    final = [e for e in events if e.type == ChatEventType.FINAL]
    assert final
    assert "memory" in final[0].payload["text"]
    assert "RAM 50% terpakai" in final[0].payload["text"]


def test_action_intent_whoami_skips_ai_summary() -> None:
    intent = _make_intent("whoami", confidence=0.95)
    intent_parser = MagicMock()
    intent_parser.parse.return_value = intent

    plan_generator = MagicMock()
    plan_generator.generate.return_value = _make_plan(intent)

    action_registry = MagicMock()
    action_registry.execute.return_value = "user@host /workspace"

    ai = MagicMock()

    uc = _make_use_case(
        intent_parser=intent_parser,
        plan_generator=plan_generator,
        action_registry=action_registry,
        ai=ai,
    )
    events = list(uc.handle("whoami", _make_ctx()))

    ai.chat.assert_not_called()
    final = [e for e in events if e.type == ChatEventType.FINAL]
    assert final[0].payload["text"] == "user@host /workspace"


def test_action_intent_ai_summary_failure_falls_back_to_raw_output() -> None:
    intent = _make_intent("memory", confidence=0.95)
    intent_parser = MagicMock()
    intent_parser.parse.return_value = intent

    plan_generator = MagicMock()
    plan_generator.generate.return_value = _make_plan(intent)

    action_registry = MagicMock()
    action_registry.execute.return_value = "RAW MEM 8G/16G"

    ai = MagicMock()
    ai.chat.side_effect = AIProviderError("ollama down")

    uc = _make_use_case(
        intent_parser=intent_parser,
        plan_generator=plan_generator,
        action_registry=action_registry,
        ai=ai,
    )
    events = list(uc.handle("cek ram", _make_ctx()))

    final = [e for e in events if e.type == ChatEventType.FINAL]
    assert final
    assert "RAW MEM 8G/16G" in final[0].payload["text"]


def test_action_intent_execution_error_yields_error_event() -> None:
    intent = _make_intent("disk", confidence=0.95)
    intent_parser = MagicMock()
    intent_parser.parse.return_value = intent

    plan_generator = MagicMock()
    plan_generator.generate.return_value = _make_plan(intent)

    action_registry = MagicMock()
    action_registry.execute.side_effect = ActionExecutionError("df failed")

    uc = _make_use_case(
        intent_parser=intent_parser,
        plan_generator=plan_generator,
        action_registry=action_registry,
    )
    events = list(uc.handle("cek disk", _make_ctx()))

    error_events = [e for e in events if e.type == ChatEventType.ERROR]
    assert error_events
    assert "df failed" in error_events[0].payload["message"]
    # No FINAL once execution fails.
    assert not [e for e in events if e.type == ChatEventType.FINAL]


# ── Action path (approval required) ───────────────────────────────────────────


def test_action_requiring_approval_yields_approval_event_and_saves_plan() -> None:
    intent = _make_intent("docker_restart", confidence=0.9)
    intent_parser = MagicMock()
    intent_parser.parse.return_value = intent

    plan = _make_plan(intent, requires_approval=True)
    plan_generator = MagicMock()
    plan_generator.generate.return_value = plan

    pending = MagicMock()
    action_registry = MagicMock()

    uc = _make_use_case(
        intent_parser=intent_parser,
        plan_generator=plan_generator,
        pending_plans=pending,
        action_registry=action_registry,
    )
    events = list(uc.handle("docker restart web", _make_ctx()))

    approval_events = [e for e in events if e.type == ChatEventType.APPROVAL_REQUIRED]
    assert approval_events
    assert approval_events[0].payload["plan_id"] == "plan-1"
    pending.save.assert_called_once()
    # Action must NOT execute once approval is needed.
    action_registry.execute.assert_not_called()


# ── Action path (intent recognized but no handler) ────────────────────────────


def test_action_intent_unknown_handler_yields_final_with_belum_ada_handler() -> None:
    # 'deploy' is action-y but NOT in EXECUTABLE_ACTIONS — must hit fallback.
    intent = _make_intent("deploy", confidence=0.9)
    intent_parser = MagicMock()
    intent_parser.parse.return_value = intent

    plan_generator = MagicMock()
    plan_generator.generate.return_value = _make_plan(intent, requires_approval=False)

    uc = _make_use_case(intent_parser=intent_parser, plan_generator=plan_generator)
    events = list(uc.handle("deploy", _make_ctx()))

    final = [e for e in events if e.type == ChatEventType.FINAL]
    assert final
    assert "belum ada handler" in final[0].payload["text"]


# ── Complex request → ExecutionLoop ───────────────────────────────────────────


def _loop_event(ev_type: str, **data: Any) -> Any:
    ev = MagicMock()
    ev.type = ev_type
    ev.data = data
    return ev


def test_complex_request_routes_to_execution_loop_when_present() -> None:
    # 'deploy' is action-ish, not in _EXPLICIT_SIMPLE_INTENTS; combined with a
    # complex trigger word ("kenapa") it routes through ExecutionLoop.
    intent = _make_intent("deploy", confidence=0.8)
    intent_parser = MagicMock()
    intent_parser.parse.return_value = intent

    history = MagicMock()
    history.recent.return_value = []

    loop = MagicMock()
    loop.run.return_value = iter([
        _loop_event("observing", message="scanning"),
        _loop_event("thinking", message="thinking..."),
        _loop_event("action_started", action="terminal", command="ls"),
        _loop_event("action_result", action="terminal", output="file1"),
        _loop_event("final", text="done"),
    ])

    uc = _make_use_case(
        intent_parser=intent_parser,
        history=history,
        execution_loop=loop,
    )
    events = list(uc.handle("kenapa server lambat", _make_ctx()))

    types = [e.type for e in events]
    assert ChatEventType.OBSERVING in types
    assert ChatEventType.THINKING in types
    assert ChatEventType.ACTION_STARTED in types
    assert ChatEventType.ACTION_RESULT in types
    final = [e for e in events if e.type == ChatEventType.FINAL]
    assert final and final[0].payload["text"] == "done"
    # Assistant history must be persisted when loop produces a final.
    assert any(
        call.args[1] == "assistant" and call.args[2] == "done"
        for call in history.append.call_args_list
    )


def test_complex_request_loop_ai_error_yields_error_event() -> None:
    intent = _make_intent("deploy", confidence=0.8)
    intent_parser = MagicMock()
    intent_parser.parse.return_value = intent

    history = MagicMock()
    history.recent.return_value = []

    loop = MagicMock()
    loop.run.side_effect = AIProviderError("LLM offline")

    uc = _make_use_case(
        intent_parser=intent_parser,
        history=history,
        execution_loop=loop,
    )
    events = list(uc.handle("kenapa container restart", _make_ctx()))

    errors = [e for e in events if e.type == ChatEventType.ERROR]
    assert errors
    assert "LLM offline" in errors[0].payload["message"]


def test_chat_injects_project_context_into_prompt() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("chat", confidence=1.0)

    ai = MagicMock()
    ai.chat_stream.return_value = iter(["ok"])

    history = MagicMock()
    history.recent.return_value = []

    context_provider = MagicMock()
    context_provider.build_context.return_value = "## Konteks project\nTugas terbuka:\n- [1] deploy"

    uc = _make_use_case(
        intent_parser=intent_parser,
        ai=ai,
        history=history,
        context_provider=context_provider,
    )
    list(uc.handle("apa tugas saya", _make_ctx(user_id="u1")))

    context_provider.build_context.assert_called_once_with("u1")
    prompt = ai.chat_stream.call_args.args[0]
    assert "Tugas terbuka:" in prompt
    assert "[1] deploy" in prompt


def test_chat_without_context_provider_omits_context_section() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("chat", confidence=1.0)

    ai = MagicMock()
    ai.chat_stream.return_value = iter(["ok"])

    history = MagicMock()
    history.recent.return_value = []

    uc = _make_use_case(intent_parser=intent_parser, ai=ai, history=history)
    list(uc.handle("halo", _make_ctx()))

    prompt = ai.chat_stream.call_args.args[0]
    assert "Konteks project" not in prompt


def test_chat_empty_context_omits_context_section() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("chat", confidence=1.0)

    ai = MagicMock()
    ai.chat_stream.return_value = iter(["ok"])

    history = MagicMock()
    history.recent.return_value = []

    context_provider = MagicMock()
    context_provider.build_context.return_value = ""

    uc = _make_use_case(
        intent_parser=intent_parser,
        ai=ai,
        history=history,
        context_provider=context_provider,
    )
    list(uc.handle("halo", _make_ctx()))

    prompt = ai.chat_stream.call_args.args[0]
    assert "Konteks project" not in prompt


def test_simple_intent_with_execution_loop_present_still_takes_action_path() -> None:
    """memory is in _EXPLICIT_SIMPLE_INTENTS — should never hit the loop."""
    intent = _make_intent("memory", confidence=0.95)
    intent_parser = MagicMock()
    intent_parser.parse.return_value = intent

    plan_generator = MagicMock()
    plan_generator.generate.return_value = _make_plan(intent)

    action_registry = MagicMock()
    action_registry.execute.return_value = "MEM OK"

    ai = MagicMock()
    ai.chat.return_value = "ringkasan"

    loop = MagicMock()

    uc = _make_use_case(
        intent_parser=intent_parser,
        plan_generator=plan_generator,
        action_registry=action_registry,
        ai=ai,
        execution_loop=loop,
    )
    events = list(uc.handle("cek ram", _make_ctx()))

    loop.run.assert_not_called()
    assert any(e.type == ChatEventType.ACTION_RESULT for e in events)
