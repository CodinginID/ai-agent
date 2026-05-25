"""Audit logging — dua sink saling melengkapi.

1. Redis Streams (``log_event`` / ``recent``) — best-effort cap di ~5000 event,
   dipakai handler/web buat fast-replay observability.
2. JSON Lines file (``JsonlAuditLogger``) — append-only, durable di disk,
   secrets-redacted. Domain ``HandleMessageUseCase`` panggil lewat port
   ``app.ports.audit.AuditLogger`` supaya tetep DI-friendly.

Format JSONL: satu event per baris, schema::

    {"ts": "2026-05-25T03:21:09.123456+00:00", "event": "request_received",
     "trace_id": "uuid-...", "user_id": "u1", ...}

Rotation: filesystem-level — kalau ukuran file > ``max_bytes`` saat write,
file di-rename ke ``audit.jsonl.1`` (overwrite previous). Sederhana, no daemon.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.adapters.redis_client import get_client, k_audit_stream

logger = logging.getLogger(__name__)

_MAX_LEN = 5000


async def log_event(
    event: str,
    *,
    user_id: str = "?",
    intent: str = "",
    agent: str = "",
    prompt: str = "",
    status: str = "ok",
    detail: str = "",
) -> None:
    """Append event ke audit stream. Best-effort — Redis down tidak boleh fail caller."""
    try:
        client = get_client()
        await client.xadd(
            k_audit_stream(),
            {
                "ts": datetime.now(UTC).isoformat(),
                "event": event,
                "user_id": user_id,
                "intent": intent,
                "agent": agent,
                "prompt_preview": prompt[:80].replace("\n", " "),
                "status": status,
                "detail": detail,
            },
            maxlen=_MAX_LEN,
            approximate=True,
        )
    except Exception as exc:
        logger.warning("audit log failed: %s", exc)


async def recent(n: int = 50, user_id: str | None = None) -> list[dict[str, Any]]:
    """Read N event terbaru. Filter user_id kalau diisi."""
    try:
        client = get_client()
        entries = await client.xrevrange(k_audit_stream(), count=max(1, n) * 5)
    except Exception as exc:
        logger.warning("audit read failed: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    for entry_id, fields in entries:
        if user_id and fields.get("user_id") != user_id:
            continue
        out.append({
            "id": entry_id,
            "ts": fields.get("ts", ""),
            "event": fields.get("event", ""),
            "user_id": fields.get("user_id", ""),
            "intent": fields.get("intent", ""),
            "agent": fields.get("agent", ""),
            "prompt_preview": fields.get("prompt_preview", ""),
            "status": fields.get("status", ""),
            "detail": fields.get("detail", ""),
        })
        if len(out) >= n:
            break
    return out


# ── JSON Lines audit logger ─────────────────────────────────────────────────

# Substring (case-insensitive) yang nandain key sensitif. Apapun yang nyentuh
# key ini di-redact jadi "***" sebelum di-serialize.
_SECRET_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
)

_REDACTED = "***"


def _redact(value: Any) -> Any:
    """Recursively redact secrets di dict/list. Scalar value lewat apa adanya."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            lowered = str(k).lower()
            if any(s in lowered for s in _SECRET_SUBSTRINGS):
                out[str(k)] = _REDACTED
            else:
                out[str(k)] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class JsonlAuditLogger:
    """Append JSON Lines ke file dengan size-based rotation.

    Bukan thread-safe across processes — multi-worker setup harus pakai
    sink terpusat (Redis stream / syslog). Single-process safe via Lock.
    """

    def __init__(self, path: Path, max_bytes: int = 10 * 1024 * 1024) -> None:
        self._path = path
        self._max_bytes = max_bytes
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def log(self, event: str, trace_id: str, **fields: Any) -> None:
        """Write satu event. Failure di-swallow + warn supaya gak ganggu caller."""
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "trace_id": trace_id,
        }
        record.update(_redact(fields))
        # ``default=str`` covers Path/UUID/datetime; broad except is intentional —
        # an audit failure must never propagate into request handling.
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.warning("audit jsonl serialize failed: %s", exc)
            return

        with self._lock:
            try:
                self._rotate_if_needed(len(line) + 1)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.write("\n")
            except OSError as exc:
                logger.warning("audit jsonl write failed: %s", exc)

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        try:
            current = self._path.stat().st_size
        except FileNotFoundError:
            return
        if current + incoming_bytes <= self._max_bytes:
            return
        rotated = self._path.with_suffix(self._path.suffix + ".1")
        try:
            os.replace(self._path, rotated)
        except OSError as exc:
            logger.warning("audit jsonl rotate failed: %s", exc)
