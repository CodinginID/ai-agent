"""Unit tests untuk ``JsonlAuditLogger`` — JSON Lines + rotation + redaction."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.audit import JsonlAuditLogger


def _read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_log_writes_jsonl_with_required_fields(tmp_path: Path) -> None:
    log = JsonlAuditLogger(path=tmp_path / "audit.jsonl")

    log.log("request_received", "trace-1", user_id="u1", text_preview="halo")

    entries = _read_lines(log.path)
    assert len(entries) == 1
    record = entries[0]
    assert record["event"] == "request_received"
    assert record["trace_id"] == "trace-1"
    assert record["user_id"] == "u1"
    assert record["text_preview"] == "halo"
    assert "ts" in record


def test_log_creates_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "audit.jsonl"

    log = JsonlAuditLogger(path=target)
    log.log("ping", "t")

    assert target.exists()
    assert len(_read_lines(target)) == 1


def test_log_redacts_known_secret_keys(tmp_path: Path) -> None:
    log = JsonlAuditLogger(path=tmp_path / "audit.jsonl")

    log.log(
        "request_received",
        "trace-1",
        telegram_bot_token="123:ABCDEF",
        api_key="sk-live-xyz",
        password="hunter2",
        nested={"refresh_token": "secret", "username": "alice"},
        safe_field="visible",
    )

    record = _read_lines(log.path)[0]
    assert record["telegram_bot_token"] == "***"
    assert record["api_key"] == "***"
    assert record["password"] == "***"
    assert record["nested"]["refresh_token"] == "***"
    assert record["nested"]["username"] == "alice"
    assert record["safe_field"] == "visible"


def test_log_rotates_when_file_exceeds_cap(tmp_path: Path) -> None:
    log = JsonlAuditLogger(path=tmp_path / "audit.jsonl", max_bytes=200)

    for i in range(20):
        log.log("noise", f"trace-{i}", payload="x" * 50)

    rotated = tmp_path / "audit.jsonl.1"
    assert rotated.exists(), "rotation must move old content to .1"
    assert log.path.exists(), "new active log must exist after rotation"
    assert log.path.stat().st_size <= 200 + 200  # current file roughly under cap


def test_log_swallows_serialization_errors(tmp_path: Path) -> None:
    log = JsonlAuditLogger(path=tmp_path / "audit.jsonl")

    class NotSerializable:
        def __repr__(self) -> str:
            raise RuntimeError("boom")

    # Should not raise — default=str fallback handles most, but if it still
    # fails the adapter must log a warning and return cleanly.
    log.log("event", "trace-1", payload=NotSerializable())


@pytest.mark.parametrize(
    "secret_key",
    ["TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "db_password", "session_secret"],
)
def test_log_redacts_case_insensitive(tmp_path: Path, secret_key: str) -> None:
    log = JsonlAuditLogger(path=tmp_path / "audit.jsonl")

    log.log("env_dump", "t", **{secret_key: "leak-me"})

    record = _read_lines(log.path)[0]
    assert record[secret_key] == "***"
