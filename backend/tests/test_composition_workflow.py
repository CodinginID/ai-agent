"""Tests untuk composition factory workflow — resolusi provider per-user."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.ollama import OllamaAdapter
from app.orchestrator.workflow import WorkflowOrchestrator

if TYPE_CHECKING:
    import pytest


class _FakeResolver:
    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def for_user(self, user_id: str) -> Any:
        return self._provider


def test_build_workflow_orchestrator_for_user_uses_resolved_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.composition as comp

    sentinel_provider = OllamaAdapter(url="http://fake", model="fake-model", timeout=1)
    monkeypatch.setattr(comp, "_provider_resolver", lambda: _FakeResolver(sentinel_provider))

    orch = comp.build_workflow_orchestrator_for_user("user-1")

    assert isinstance(orch, WorkflowOrchestrator)
    assert orch.architect.ai is sentinel_provider  # type: ignore[attr-defined]
    assert orch.engineer.ai is sentinel_provider  # type: ignore[attr-defined]
    assert orch.reviewer.ai is sentinel_provider  # type: ignore[attr-defined]


def test_build_workflow_orchestrator_for_user_not_cached_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tidak boleh di-lru_cache — provider bisa berubah antar request (personal key)."""
    import app.composition as comp

    provider_a = OllamaAdapter(url="http://a", model="a", timeout=1)
    provider_b = OllamaAdapter(url="http://b", model="b", timeout=1)
    providers = iter([provider_a, provider_b])

    class _RotatingResolver:
        def for_user(self, user_id: str) -> Any:
            return next(providers)

    monkeypatch.setattr(comp, "_provider_resolver", lambda: _RotatingResolver())

    orch1 = comp.build_workflow_orchestrator_for_user("same-user")
    orch2 = comp.build_workflow_orchestrator_for_user("same-user")

    assert orch1.architect.ai is provider_a  # type: ignore[attr-defined]
    assert orch2.architect.ai is provider_b  # type: ignore[attr-defined]
