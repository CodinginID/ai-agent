"""Unit tests for Docker Compose actions in docker_ops.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.actions.docker_ops import (
    DockerComposeBuildAction,
    DockerComposePsAction,
    DockerComposePullAction,
    DockerComposeRestartAction,
    DockerComposeUpAction,
)

_PROJECT = Path("/fake/project")


def _mock_run_safe(output: str = "", returncode: int = 0):
    return patch("app.actions.docker_ops.run_safe", return_value=(output, returncode))


# ── DockerComposePsAction ──────────────────────────────────────────────────────

def test_compose_ps_calls_docker_compose_ps() -> None:
    with _mock_run_safe("service   running") as mock:
        result = DockerComposePsAction(project_dir=_PROJECT).execute()
    mock.assert_called_once_with(["docker", "compose", "ps"], cwd=_PROJECT)
    assert "running" in result


def test_compose_ps_returns_fallback_when_empty() -> None:
    with _mock_run_safe(""):
        result = DockerComposePsAction(project_dir=_PROJECT).execute()
    assert "Tidak ada" in result


# ── DockerComposePullAction ────────────────────────────────────────────────────

def test_compose_pull_calls_correct_command() -> None:
    with _mock_run_safe("Pulling...") as mock:
        DockerComposePullAction(project_dir=_PROJECT).execute()
    args = mock.call_args[0][0]
    assert args == ["docker", "compose", "pull"]


def test_compose_pull_returns_error_on_failure() -> None:
    with _mock_run_safe("network error", returncode=1):
        result = DockerComposePullAction(project_dir=_PROJECT).execute()
    assert "gagal" in result


def test_compose_pull_returns_fallback_on_empty_success() -> None:
    with _mock_run_safe(""):
        result = DockerComposePullAction(project_dir=_PROJECT).execute()
    assert "berhasil" in result


# ── DockerComposeBuildAction ───────────────────────────────────────────────────

def test_compose_build_calls_correct_command() -> None:
    with _mock_run_safe("") as mock:
        DockerComposeBuildAction(project_dir=_PROJECT).execute()
    args = mock.call_args[0][0]
    assert args == ["docker", "compose", "build"]


def test_compose_build_adds_no_cache_flag() -> None:
    with _mock_run_safe("") as mock:
        DockerComposeBuildAction(project_dir=_PROJECT).execute({"no_cache": True})
    args = mock.call_args[0][0]
    assert "--no-cache" in args


def test_compose_build_returns_error_on_failure() -> None:
    with _mock_run_safe("build failed", returncode=1):
        result = DockerComposeBuildAction(project_dir=_PROJECT).execute()
    assert "gagal" in result


# ── DockerComposeUpAction ──────────────────────────────────────────────────────

def test_compose_up_calls_correct_command() -> None:
    with _mock_run_safe("") as mock:
        DockerComposeUpAction(project_dir=_PROJECT).execute()
    args = mock.call_args[0][0]
    assert args == ["docker", "compose", "up", "-d", "--remove-orphans"]


def test_compose_up_returns_error_on_failure() -> None:
    with _mock_run_safe("port conflict", returncode=1):
        result = DockerComposeUpAction(project_dir=_PROJECT).execute()
    assert "gagal" in result


def test_compose_up_returns_fallback_on_empty_success() -> None:
    with _mock_run_safe(""):
        result = DockerComposeUpAction(project_dir=_PROJECT).execute()
    assert "berhasil" in result


# ── DockerComposeRestartAction ─────────────────────────────────────────────────

def test_compose_restart_no_service_restarts_all() -> None:
    with _mock_run_safe("") as mock:
        DockerComposeRestartAction(project_dir=_PROJECT).execute({})
    args = mock.call_args[0][0]
    assert args == ["docker", "compose", "restart"]


def test_compose_restart_with_service_appends_name() -> None:
    with _mock_run_safe("") as mock:
        DockerComposeRestartAction(project_dir=_PROJECT).execute({"service": "web"})
    args = mock.call_args[0][0]
    assert "web" in args


def test_compose_restart_rejects_invalid_service_name() -> None:
    result = DockerComposeRestartAction(project_dir=_PROJECT).execute(
        {"service": "bad;name&&rm -rf"}
    )
    assert "tidak valid" in result.lower()


def test_compose_restart_returns_error_on_failure() -> None:
    with _mock_run_safe("error", returncode=1):
        result = DockerComposeRestartAction(project_dir=_PROJECT).execute()
    assert "gagal" in result
