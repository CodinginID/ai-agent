"""Unit tests for app/actions/git_ops.py — subprocess calls are mocked."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.actions.git_ops import (
    GitAddAction,
    GitBranchAction,
    GitCommitAction,
    GitDiffAction,
    GitLogAction,
    GitPushAction,
    GitStatusAction,
)


_PROJECT = Path("/fake/project")


def _mock_run_safe(output: str = "", returncode: int = 0):
    """Return a patch target that replaces run_safe with a fixed (output, code) pair."""
    return patch(
        "app.actions.git_ops.run_safe",
        return_value=(output, returncode),
    )


# ── GitStatusAction ────────────────────────────────────────────────────────────

def test_git_status_calls_correct_args() -> None:
    with _mock_run_safe("## main\nM app/bot.py") as mock:
        action = GitStatusAction(project_dir=_PROJECT)
        result = action.execute()

    mock.assert_called_once_with(
        ["git", "status", "--short", "--branch"],
        cwd=_PROJECT,
    )
    assert "main" in result


# ── GitDiffAction ──────────────────────────────────────────────────────────────

def test_git_diff_unstaged_by_default() -> None:
    with _mock_run_safe("diff output") as mock:
        action = GitDiffAction(project_dir=_PROJECT)
        action.execute({})

    args_called = mock.call_args[0][0]
    assert args_called == ["git", "diff"]


def test_git_diff_staged_adds_cached_flag() -> None:
    with _mock_run_safe("staged diff") as mock:
        action = GitDiffAction(project_dir=_PROJECT)
        action.execute({"staged": True})

    args_called = mock.call_args[0][0]
    assert "--cached" in args_called


def test_git_diff_empty_returns_no_changes_message() -> None:
    with _mock_run_safe(""):
        action = GitDiffAction(project_dir=_PROJECT)
        result = action.execute({})

    assert "tidak ada perubahan" in result.lower()


# ── GitLogAction ──────────────────────────────────────────────────────────────

def test_git_log_default_10_entries() -> None:
    with _mock_run_safe("abc123 commit one") as mock:
        action = GitLogAction(project_dir=_PROJECT)
        action.execute({})

    args_called = mock.call_args[0][0]
    assert "-10" in args_called


def test_git_log_custom_n() -> None:
    with _mock_run_safe("log") as mock:
        action = GitLogAction(project_dir=_PROJECT)
        action.execute({"n": 5})

    args_called = mock.call_args[0][0]
    assert "-5" in args_called


def test_git_log_caps_at_50() -> None:
    with _mock_run_safe("log") as mock:
        action = GitLogAction(project_dir=_PROJECT)
        action.execute({"n": 999})

    args_called = mock.call_args[0][0]
    assert "-50" in args_called


# ── GitAddAction ──────────────────────────────────────────────────────────────

def test_git_add_specific_files() -> None:
    with _mock_run_safe("") as mock:
        action = GitAddAction(project_dir=_PROJECT)
        action.execute({"files": ["app/bot.py", "app/config.py"]})

    args_called = mock.call_args[0][0]
    assert "app/bot.py" in args_called
    assert "app/config.py" in args_called


def test_git_add_defaults_to_dot() -> None:
    with _mock_run_safe("") as mock:
        action = GitAddAction(project_dir=_PROJECT)
        action.execute({})

    args_called = mock.call_args[0][0]
    assert "." in args_called


def test_git_add_returns_success_message() -> None:
    with _mock_run_safe("", returncode=0):
        action = GitAddAction(project_dir=_PROJECT)
        result = action.execute({"files": ["README.md"]})

    assert "stage" in result.lower() or "README.md" in result


# ── GitCommitAction ───────────────────────────────────────────────────────────

def test_git_commit_requires_message() -> None:
    action = GitCommitAction(project_dir=_PROJECT)
    result = action.execute({})
    assert "message" in result.lower()


def test_git_commit_passes_message() -> None:
    with _mock_run_safe("[main abc] feat: test") as mock:
        action = GitCommitAction(project_dir=_PROJECT)
        result = action.execute({"message": "feat: test"})

    args_called = mock.call_args[0][0]
    assert "feat: test" in args_called
    assert "[main" in result


def test_git_commit_failure_returns_error() -> None:
    with _mock_run_safe("nothing to commit", returncode=1):
        action = GitCommitAction(project_dir=_PROJECT)
        result = action.execute({"message": "test"})

    assert "gagal" in result.lower()


# ── GitPushAction ─────────────────────────────────────────────────────────────

def test_git_push_default_remote_is_origin() -> None:
    with _mock_run_safe("") as mock:
        action = GitPushAction(project_dir=_PROJECT)
        action.execute({})

    args_called = mock.call_args[0][0]
    assert "origin" in args_called


def test_git_push_rejects_invalid_remote_name() -> None:
    action = GitPushAction(project_dir=_PROJECT)
    result = action.execute({"remote": "bad;name&&rm -rf"})
    assert "tidak valid" in result.lower()


# ── GitBranchAction ───────────────────────────────────────────────────────────

def test_git_branch_list_when_no_name() -> None:
    with _mock_run_safe("* main\n  dev") as mock:
        action = GitBranchAction(project_dir=_PROJECT)
        result = action.execute({})

    args_called = mock.call_args[0][0]
    assert args_called == ["git", "branch", "-a"]
    assert "main" in result


def test_git_branch_create_when_name_given() -> None:
    with _mock_run_safe("Switched to a new branch 'feat/x'") as mock:
        action = GitBranchAction(project_dir=_PROJECT)
        result = action.execute({"name": "feat/x"})

    args_called = mock.call_args[0][0]
    assert "feat/x" in args_called
    assert "Switched" in result


def test_git_branch_rejects_invalid_name() -> None:
    action = GitBranchAction(project_dir=_PROJECT)
    result = action.execute({"name": "branch;rm -rf"})
    assert "tidak valid" in result.lower()
