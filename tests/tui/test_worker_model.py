"""Tests for worker agent model threading (PR-2).

Verifies the per-job model is passed through to agent runners. Uses the echo
agent (no external CLI) which surfaces the model in its first chunk.
"""

from __future__ import annotations

from app.tui._worker import _AGENTS, _agent_echo


async def _drain(gen):  # type: ignore[no-untyped-def]
    return [ev async for ev in gen]


async def test_echo_agent_accepts_model_kwarg() -> None:
    events = await _drain(_agent_echo("hello", "test-model"))
    first = events[0]["text"]
    assert "echo:test-model" in first


async def test_echo_agent_without_model() -> None:
    events = await _drain(_agent_echo("hello"))
    assert events[0]["text"].startswith("[echo]")


def test_all_agent_runners_accept_model_param() -> None:
    """Every runner must accept (prompt, model) so dispatch can thread a model."""
    import inspect

    for name, runner in _AGENTS.items():
        sig = inspect.signature(runner)
        params = list(sig.parameters)
        assert "model" in params, f"agent runner {name!r} missing 'model' param"
