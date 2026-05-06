"""Worker presence registry — Redis-backed.

Tiap worker (TUI di mesin user) yang konek WS akan:
- ``SADD workers:<user_id> <worker_id>`` untuk register
- ``EXPIRE workers:<user_id>`` di-refresh per heartbeat
- ``HSET worker:meta:<worker_id>`` untuk metadata (host, version, connected_at)
- ``SREM`` saat disconnect

Backend dispatcher pakai registry ini untuk:
- Cek user-id punya worker online atau tidak
- Pilih worker mana untuk dispatch (random/round-robin)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.adapters.redis_client import get_client, k_worker_meta, k_workers

logger = logging.getLogger(__name__)

# TTL set member — di-refresh per heartbeat. Kalau worker mati tanpa unregister,
# Redis akan auto-purge setelah TTL expire.
WORKER_TTL_SEC = 60


async def register(
    user_id: str,
    worker_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Tandai worker_id aktif untuk user_id. Refresh TTL set."""
    client = get_client()
    pipe = client.pipeline()
    pipe.sadd(k_workers(user_id), worker_id)
    pipe.expire(k_workers(user_id), WORKER_TTL_SEC)
    pipe.hset(
        k_worker_meta(worker_id),
        mapping={
            "user_id": user_id,
            "connected_at": datetime.now(UTC).isoformat(),
            **(metadata or {}),
        },
    )
    pipe.expire(k_worker_meta(worker_id), WORKER_TTL_SEC)
    await pipe.execute()


async def heartbeat(user_id: str, worker_id: str) -> None:
    """Perpanjang TTL — dipanggil tiap N detik dari worker side."""
    client = get_client()
    pipe = client.pipeline()
    pipe.expire(k_workers(user_id), WORKER_TTL_SEC)
    pipe.expire(k_worker_meta(worker_id), WORKER_TTL_SEC)
    await pipe.execute()


async def unregister(user_id: str, worker_id: str) -> None:
    """Bersihkan saat worker disconnect."""
    from app.adapters.redis_client import k_caps
    client = get_client()
    pipe = client.pipeline()
    pipe.srem(k_workers(user_id), worker_id)
    pipe.delete(k_worker_meta(worker_id))
    # Bersihkan capability set juga (TTL akan handle juga, tapi explicit lebih cepat)
    for agent_id in ("codex", "claude", "glm"):
        pipe.srem(k_caps(user_id, agent_id), worker_id)
    await pipe.execute()


async def list_workers(user_id: str) -> list[str]:
    """Daftar worker_id yang aktif untuk user_id."""
    client = get_client()
    members = await client.smembers(k_workers(user_id))
    return list(members)


async def worker_count(user_id: str) -> int:
    client = get_client()
    return int(await client.scard(k_workers(user_id)))


async def get_meta(worker_id: str) -> dict[str, str]:
    client = get_client()
    data = await client.hgetall(k_worker_meta(worker_id))
    return dict(data)
