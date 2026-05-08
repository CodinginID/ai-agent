"""Unit tests for deploy workflow actions — subprocess and HTTP calls are mocked."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from app.actions.deploy import DeployAction, ServiceHealthCheckAction

_PROJECT = Path("/fake/project")


def _mock_run_safe(outputs: list[tuple[str, int]]):
    """Side-effect that returns successive (output, returncode) pairs."""
    return patch("app.actions.deploy.run_safe", side_effect=outputs)


# ── ServiceHealthCheckAction ──────────────────────────────────────────────────

def _mock_get(status_code: int = 200, elapsed_s: float = 0.1):
    resp = MagicMock()
    resp.ok = status_code < 400
    resp.status_code = status_code
    resp.elapsed.total_seconds.return_value = elapsed_s
    return patch("requests.get", return_value=resp)


def test_health_check_returns_up_on_2xx() -> None:
    with _mock_get(200):
        result = ServiceHealthCheckAction().execute({"url": "http://localhost/health"})
    assert "UP" in result
    assert "200" in result


def test_health_check_returns_warning_on_5xx() -> None:
    with _mock_get(503):
        result = ServiceHealthCheckAction().execute({"url": "http://localhost/health"})
    assert "503" in result


def test_health_check_returns_down_on_connection_error() -> None:
    with patch("requests.get", side_effect=requests.ConnectionError()):
        result = ServiceHealthCheckAction().execute({"url": "http://localhost/health"})
    assert "DOWN" in result


def test_health_check_returns_timeout_message() -> None:
    with patch("requests.get", side_effect=requests.Timeout()):
        result = ServiceHealthCheckAction().execute({"url": "http://localhost/health"})
    assert "TIMEOUT" in result


def test_health_check_requires_url_param() -> None:
    result = ServiceHealthCheckAction().execute({})
    assert "url" in result.lower()


def test_health_check_rejects_non_http_url() -> None:
    result = ServiceHealthCheckAction().execute({"url": "ftp://bad"})
    assert "http" in result.lower()


# ── DeployAction ──────────────────────────────────────────────────────────────

def test_deploy_name_and_description() -> None:
    action = DeployAction(project_dir=_PROJECT)
    assert action.name == "deploy"
    assert "deploy" in action.description.lower()


def test_deploy_happy_path_returns_success_message() -> None:
    outputs = [
        ("abc1234", 0),         # git rev-parse HEAD
        ("Already up to date.", 0),  # git pull
        ("", 0),                # docker compose build
        ("", 0),                # docker compose up
    ]
    with _mock_run_safe(outputs):
        result = DeployAction(project_dir=_PROJECT).execute()
    assert "Deploy selesai" in result
    assert "pre_deploy_commit: abc1234" in result


def test_deploy_aborts_when_git_pull_fails() -> None:
    outputs = [
        ("abc1234", 0),   # git rev-parse HEAD
        ("conflict", 1),  # git pull — fail
    ]
    with _mock_run_safe(outputs):
        result = DeployAction(project_dir=_PROJECT).execute()
    assert "git pull gagal" in result or "dibatalkan" in result


def test_deploy_aborts_when_build_fails() -> None:
    outputs = [
        ("abc1234", 0),
        ("ok", 0),       # git pull
        ("error", 1),    # docker compose build — fail
    ]
    with _mock_run_safe(outputs):
        result = DeployAction(project_dir=_PROJECT).execute()
    assert "Build gagal" in result or "dibatalkan" in result


def test_deploy_runs_health_check_when_url_set() -> None:
    outputs = [
        ("abc1234", 0),
        ("ok", 0),
        ("", 0),
        ("", 0),
    ]
    with _mock_run_safe(outputs), _mock_get(200):
        result = DeployAction(project_dir=_PROJECT, health_url="http://app/health").execute()
    assert "UP" in result or "health" in result.lower()


def test_deploy_no_cache_flag_passed_when_requested() -> None:
    calls: list[list[str]] = []

    def capturing_run_safe(cmd: list[str], **kw: object) -> tuple[str, int]:
        calls.append(cmd)
        return ("", 0)

    with patch("app.actions.deploy.run_safe", side_effect=capturing_run_safe):
        DeployAction(project_dir=_PROJECT).execute({"no_cache": True})

    build_call = next((c for c in calls if "build" in c), None)
    assert build_call is not None
    assert "--no-cache" in build_call
