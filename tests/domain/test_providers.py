"""Tests for the shared provider constants/helpers (single source of truth)."""

from __future__ import annotations

from app.domain.providers import (
    ALL_PROVIDERS,
    CLI_PROVIDERS,
    CLOUD_PROVIDERS,
    is_cli_provider,
)


def test_all_providers_is_union_of_cloud_cli_mock() -> None:
    assert CLOUD_PROVIDERS | CLI_PROVIDERS | {"mock"} == ALL_PROVIDERS


def test_cloud_providers_are_anthropic_and_glm() -> None:
    assert {"anthropic", "glm"} == CLOUD_PROVIDERS


def test_cli_providers_are_claude_cli_and_glm_cli() -> None:
    assert {"claude-cli", "glm-cli"} == CLI_PROVIDERS


def test_is_cli_provider_true_for_cli_names() -> None:
    assert is_cli_provider("claude-cli") is True
    assert is_cli_provider("glm-cli") is True
    assert is_cli_provider(" Claude-CLI ") is True


def test_is_cli_provider_false_for_others() -> None:
    assert is_cli_provider("anthropic") is False
    assert is_cli_provider("glm") is False
    assert is_cli_provider("mock") is False
    assert is_cli_provider("") is False
