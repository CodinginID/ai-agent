"""Audit log via Redis Streams.

Setiap event penting (chat send, agent dispatch, agent done) di-XADD ke
``audit:stream``. Read-side: XREVRANGE atau XLEN untuk replay/observability.

Format event (fields-pairs di Stream):
- ts            : ISO timestamp UTC
- event         : event_type (chat_send | agent_dispatch | agent_done | agent_error)
- user_id       : UUID user (atau "?")
- intent        : intent name (kalau ada)
- agent         : agent name (kalau ada)
- prompt_preview: 80 char pertama dari prompt
- status        : ok | error | started
- detail        : optional extra info
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.adapters.redis_client import get_client, k_audit_stream

logger = logging.getLogger(__name__)

# Cap stream supaya tidak grow infinite — keep ~last 5000 events.
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
