"""Tests for the provider→agent routing override in WorkerDispatchAdapter.

Only the pure mapping is tested here (``_PROVIDER_AGENT``); the async
dispatch/caps machinery is exercised elsewhere via composition-level tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.worker_dispatch import _PROVIDER_AGENT, _single_agent_override

if TYPE_CHECKING:
    import pytest


def test_claude_cli_maps_to_claude_agent() -> None:
    assert _PROVIDER_AGENT["claude-cli"] == "claude"


def test_glm_cli_maps_to_glm_agent() -> None:
    assert _PROVIDER_AGENT["glm-cli"] == "glm"


def test_existing_cloud_aliases_unchanged() -> None:
    assert _PROVIDER_AGENT["claude"] == "claude"
    assert _PROVIDER_AGENT["anthropic"] == "claude"
    assert _PROVIDER_AGENT["glm"] == "glm"
    assert _PROVIDER_AGENT["zhipu"] == "glm"


class _FakeRepo:
    def __init__(self, pref: tuple[str, str | None] | None) -> None:
        self._pref = pref

    def get(self, user_id: str) -> tuple[str, str | None] | None:
        return self._pref


def test_single_agent_override_claude_cli_routes_to_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.user_provider_config as upc_mod

    monkeypatch.setattr(
        upc_mod,
        "UserProviderConfigRepository",
        lambda factory: _FakeRepo(("claude-cli", None)),
    )
    assert _single_agent_override("u1") == "claude"


def test_single_agent_override_glm_cli_routes_to_glm(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.user_provider_config as upc_mod

    monkeypatch.setattr(
        upc_mod,
        "UserProviderConfigRepository",
        lambda factory: _FakeRepo(("glm-cli", None)),
    )
    assert _single_agent_override("u1") == "glm"


def test_single_agent_override_mock_is_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.user_provider_config as upc_mod

    monkeypatch.setattr(
        upc_mod, "UserProviderConfigRepository", lambda factory: _FakeRepo(("mock", None))
    )
    assert _single_agent_override("u1") is None


def test_single_agent_override_empty_user_id_is_none() -> None:
    assert _single_agent_override("") is None
