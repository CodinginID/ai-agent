# tests/adapters/test_mock_llm.py
from __future__ import annotations

import json

from app.adapters.ai_provider_factory import build_ai_provider
from app.adapters.circuit_breaker import _CircuitBreakerProvider
from app.adapters.mock_llm import MockAIProvider
from app.config import load_settings


def test_intent_prompt_returns_valid_intent_json() -> None:
    out = MockAIProvider().chat("You are a strict JSON intent parser for a bot.")
    data = json.loads(out)
    assert data["intent"] == "chat"
    assert data["requires_approval"] is False


def test_planning_prompt_returns_plan_with_steps() -> None:
    out = MockAIProvider().chat("You are a Project Manager AI. Break down this request.")
    data = json.loads(out)
    assert len(data["steps"]) == 2
    assert data["steps"][0]["action"] == "server_status"


def test_loop_think_returns_respond_action() -> None:
    prompt = 'Respond ONLY with valid JSON. {"action": "terminal", "command": "ls"}'
    data = json.loads(MockAIProvider().chat(prompt))
    assert data["action"] == "respond"


def test_reflect_returns_satisfied() -> None:
    data = json.loads(MockAIProvider().chat("Did this fully address the request?"))
    assert data["satisfied"] is True


def test_chat_fallback_is_plain_text() -> None:
    out = MockAIProvider().chat("halo apa kabar")
    assert out.startswith("[mock]")


def test_chat_stream_concatenates_to_chat() -> None:
    m = MockAIProvider()
    prompt = "halo"
    assert "".join(m.chat_stream(prompt)) == m.chat(prompt)


def test_factory_mock_needs_no_key() -> None:
    provider = build_ai_provider("mock", None, load_settings())
    assert isinstance(provider, _CircuitBreakerProvider)
    assert isinstance(provider._inner, MockAIProvider)
