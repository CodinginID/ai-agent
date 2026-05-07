"""Job state persistence via Redis hash.

Tujuannya:
- Survive backend restart untuk visibility (what was running when we died?)
- Idempotent: caller bisa cek status by job_id
- Cross-instance routing (B5g): originator field tahu instance mana yang harus
  receive worker reply
- Debug & audit: trace lifecycle satu job

State machine:
    dispatched → running → done | error | abandoned

TTL hash: ~1 jam — cukup untuk debug, gak grow infinite.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.adapters.redis_client import get_client, k_job

logger = logging.getLogger(__name__)

JOB_TTL_SEC = 3600  # 1 hour


async def create(
    job_id: str,
    *,
    user_id: str,
    worker_id: str,
    agent: str,
    prompt: str,
    originator_instance: str,
) -> None:
    """Bikin record job baru — dipanggil saat dispatcher kirim ke worker."""
    client = get_client()
    now = datetime.now(UTC).isoformat()
    pipe = client.pipeline()
    pipe.hset(k_job(job_id), mapping={
        "status": "dispatched",
        "user_id": user_id,
        "worker_id": worker_id,
        "agent": agent,
        "prompt_preview": prompt[:200].replace("\n", " "),
        "originator_instance": originator_instance,
        "created_at": now,
        "updated_at": now,
    })
    pipe.expire(k_job(job_id), JOB_TTL_SEC)
    await pipe.execute()


async def update_status(
    job_id: str,
    status: str,
    *,
    summary: str = "",
    error: str = "",
) -> None:
    """Update status — dipanggil saat job_started/done/error datang."""
    client = get_client()
    now = datetime.now(UTC).isoformat()
    fields: dict[str, str] = {
        "status": status,
        "updated_at": now,
    }
    if summary:
        fields["summary"] = summary
    if error:
        fields["error"] = error
    if status == "running":
        fields["started_at"] = now
    if status in ("done", "error", "abandoned"):
        fields["finished_at"] = now
    await client.hset(k_job(job_id), mapping=fields)
    await client.expire(k_job(job_id), JOB_TTL_SEC)


async def get(job_id: str) -> dict[str, Any] | None:
    client = get_client()
    data = await client.hgetall(k_job(job_id))
    return dict(data) if data else None


async def mark_abandoned_for_instance(instance_id: str) -> int:
    """Backend startup: tandai semua job yang originator-nya kita & masih running
    sebagai ``abandoned`` — jelas user kalau ada job yang gak akan complete.

    Pakai SCAN supaya gak block Redis walau ada banyak job. Return jumlah yang
    di-mark.
    """
    client = get_client()
    n = 0
    cursor = 0
    while True:
        cursor, keys = await client.scan(cursor=cursor, match="job:*", count=200)
        for key in keys:
            data = await client.hgetall(key)
            if not data:
                continue
            if data.get("originator_instance") != instance_id:
                continue
            if data.get("status") not in ("dispatched", "running"):
                continue
            await client.hset(key, mapping={
                "status": "abandoned",
                "updated_at": datetime.now(UTC).isoformat(),
                "error": "backend restart — job tidak complete",
            })
            n += 1
        if cursor == 0:
            break
    return n
