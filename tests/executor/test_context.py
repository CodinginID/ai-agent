"""Tests for ContextCollector — using subprocess mocks, no real shell calls."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.executor.context import ContextCollector, EnvironmentContext, _run_quietly


# ── _run_quietly unit tests ────────────────────────────────────────────────────

def test_run_quietly_returns_stdout_on_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "hello world\n"
        mock_run.return_value.returncode = 0
        result = _run_quietly(["echo", "hello world"])
    assert result == "hello world"


def test_run_quietly_returns_error_message_when_command_not_found() -> None:
    import subprocess
    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = _run_quietly(["nonexistent-command"])
    assert "not found" in result


def test_run_quietly_returns_timeout_message_on_timeout() -> None:
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=8)):
        result = _run_quietly(["slow-command"])
    assert "timeout" in result


def test_run_quietly_handles_oserror() -> None:
    with patch("subprocess.run", side_effect=OSError("permission denied")):
        result = _run_quietly(["bad-command"])
    assert "error" in result


# ── EnvironmentContext render tests ───────────────────────────────────────────

def test_environment_context_render_contains_all_fields() -> None:
    ctx = EnvironmentContext(
        git_status="M app/bot.py",
        docker_ps="aiagent_bot   Up 2 hours",
        repo_files="app/bot.py\napp/config.py",
        hostname="vps-prod-01",
        working_dir="/app",
        collected_at=datetime.now(),
    )
    rendered = ctx.render()
    assert "vps-prod-01" in rendered
    assert "/app" in rendered
    assert "M app/bot.py" in rendered
    assert "aiagent_bot" in rendered
    assert "app/config.py" in rendered


def test_environment_context_render_fallback_message_when_empty() -> None:
    ctx = EnvironmentContext(
        git_status="",
        docker_ps="",
        repo_files="",
        hostname="host",
        working_dir="/tmp",
        collected_at=datetime.now(),
    )
    rendered = ctx.render()
    assert "(no git repo)" in rendered
    assert "(docker not available)" in rendered
    assert "(not a git repo)" in rendered


# ── ContextCollector caching tests ───────────────────────────────────────────

def _make_collector(tmp_path: Path) -> ContextCollector:
    return ContextCollector(working_dir=tmp_path, ttl_seconds=30)


def _mock_fresh_env(hostname: str = "host") -> EnvironmentContext:
    return EnvironmentContext(
        git_status="",
        docker_ps="",
        repo_files="",
        hostname=hostname,
        working_dir="/tmp",
        collected_at=datetime.now(),
    )


def test_collect_caches_result_within_ttl(tmp_path: Path) -> None:
    collector = _make_collector(tmp_path)

    call_count = 0

    def fake_collect_fresh() -> EnvironmentContext:
        nonlocal call_count
        call_count += 1
        return _mock_fresh_env(hostname=f"call-{call_count}")

    collector._collect_fresh = fake_collect_fresh  # type: ignore[method-assign]

    first = collector.collect()
    second = collector.collect()

    assert first is second   # same cached object
    assert call_count == 1   # only collected once


def test_collect_invalidate_forces_recollect(tmp_path: Path) -> None:
    collector = _make_collector(tmp_path)
    call_count = 0

    def fake_collect_fresh() -> EnvironmentContext:
        nonlocal call_count
        call_count += 1
        return _mock_fresh_env(hostname=f"call-{call_count}")

    collector._collect_fresh = fake_collect_fresh  # type: ignore[method-assign]

    collector.collect()
    collector.invalidate()
    second = collector.collect()

    assert call_count == 2
    assert second.hostname == "call-2"


def test_collect_re_fetches_after_ttl_expired(tmp_path: Path) -> None:
    collector = ContextCollector(working_dir=tmp_path, ttl_seconds=0)  # always expired
    call_count = 0

    def fake_collect_fresh() -> EnvironmentContext:
        nonlocal call_count
        call_count += 1
        return _mock_fresh_env()

    collector._collect_fresh = fake_collect_fresh  # type: ignore[method-assign]

    collector.collect()
    collector.collect()

    assert call_count == 2


def test_collect_fresh_caps_repo_files_at_50_lines(tmp_path: Path) -> None:
    """repo_files should show at most 50 lines from git ls-files output."""
    many_files = "\n".join(f"file_{i}.py" for i in range(100))

    with patch("app.executor.context._run_quietly") as mock_run:
        mock_run.side_effect = lambda args, **kw: (
            "hostname-test" if args[0] == "hostname" else
            "" if args[0] == "git" and "status" in args else
            many_files if args[0] == "git" and "ls-files" in args else
            ""
        )
        collector = ContextCollector(working_dir=tmp_path)
        ctx = collector._collect_fresh()

    lines = ctx.repo_files.splitlines()
    assert len(lines) == 50
