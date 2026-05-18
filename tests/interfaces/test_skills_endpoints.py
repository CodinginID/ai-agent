"""Unit tests untuk helper di ``app.interfaces.skills``.

Project belum punya FastAPI TestClient infra global, jadi test fokus ke
helper layer yang kompleks: auth resolver + serializer + SSE formatter.
Endpoint logic CRUD (yang cuma forward ke repository) sudah ditest di
``tests/adapters/test_skill_repository.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.interfaces.skills import (
    _format_sse,
    _resolve_user_id,
    _skill_to_response,
)
from app.orchestrator.skill_executor import SkillEvent

# ── _resolve_user_id ─────────────────────────────────────────────────────────


def test_resolve_user_id_raises_401_without_bearer() -> None:
    with pytest.raises(HTTPException) as exc:
        _resolve_user_id(None)
    assert exc.value.status_code == 401
    assert "Missing Bearer token" in str(exc.value.detail)


def test_resolve_user_id_raises_401_on_malformed_header() -> None:
    with pytest.raises(HTTPException) as exc:
        _resolve_user_id("Basic abc123")
    assert exc.value.status_code == 401


def test_resolve_user_id_raises_401_on_unknown_session_token() -> None:
    fake_repo = MagicMock()
    fake_repo.resolve.return_value = None
    with (
        patch("app.interfaces.skills.UserSessionRepository", return_value=fake_repo),
        patch("app.interfaces.skills._session_factory", return_value=MagicMock()),
        pytest.raises(HTTPException) as exc,
    ):
        _resolve_user_id("Bearer not-a-real-token")
    assert exc.value.status_code == 401
    assert "invalid or expired" in str(exc.value.detail)


def test_resolve_user_id_returns_user_id_on_valid_session() -> None:
    fake_info = MagicMock(user_id="user-42")
    fake_repo = MagicMock()
    fake_repo.resolve.return_value = fake_info
    with (
        patch("app.interfaces.skills.UserSessionRepository", return_value=fake_repo),
        patch("app.interfaces.skills._session_factory", return_value=MagicMock()),
    ):
        assert _resolve_user_id("Bearer good-token") == "user-42"
    fake_repo.resolve.assert_called_once_with("good-token")


# ── _skill_to_response ───────────────────────────────────────────────────────


def test_skill_to_response_serializes_timestamps() -> None:
    row = MagicMock()
    row.id = "skill-1"
    row.project_id = "proj-1"
    row.name = "test"
    row.description = "desc"
    row.definition = {"name": "test", "steps": []}
    row.created_at = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    row.updated_at = datetime(2026, 5, 18, 13, 30, 0, tzinfo=UTC)

    out = _skill_to_response(row)
    assert out["id"] == "skill-1"
    assert out["project_id"] == "proj-1"
    assert out["name"] == "test"
    assert out["description"] == "desc"
    assert out["definition"] == {"name": "test", "steps": []}
    assert out["created_at"] == "2026-05-18T12:00:00+00:00"
    assert out["updated_at"] == "2026-05-18T13:30:00+00:00"


def test_skill_to_response_handles_none_timestamps() -> None:
    row = MagicMock()
    row.id = "s"
    row.project_id = "p"
    row.name = "n"
    row.description = ""
    row.definition = {}
    row.created_at = None
    row.updated_at = None
    out = _skill_to_response(row)
    assert out["created_at"] is None
    assert out["updated_at"] is None


# ── _format_sse ──────────────────────────────────────────────────────────────


def test_format_sse_emits_event_and_data_lines() -> None:
    ev = SkillEvent("step_started", {"step_name": "design", "agent": "glm"})
    out = _format_sse(ev)
    lines = out.strip().split("\n")
    assert lines[0] == "event: step_started"
    assert lines[1].startswith("data: ")
    payload = json.loads(lines[1][len("data: "):])
    assert payload == {"step_name": "design", "agent": "glm"}
    # Two trailing newlines for SSE event separator
    assert out.endswith("\n\n")


def test_format_sse_empty_payload_still_valid() -> None:
    ev = SkillEvent("skill_started")
    out = _format_sse(ev)
    assert "event: skill_started" in out
    assert "data: {}" in out


def test_format_sse_payload_is_valid_json() -> None:
    """SSE consumers (TUI _skill_run, browser EventSource) butuh data:
    valid JSON yang bisa di-parse."""
    ev = SkillEvent("step_chunk", {"step_name": "x", "text": "line with \"quotes\" and\nnewline"})
    out = _format_sse(ev)
    data_line = next(
        line for line in out.split("\n") if line.startswith("data: ")
    )
    parsed = json.loads(data_line[len("data: "):])
    assert parsed["text"] == 'line with "quotes" and\nnewline'
