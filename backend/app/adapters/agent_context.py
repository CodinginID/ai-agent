"""Shared agent context — hand-off output antar role dalam satu project.

Use case: user `/code refactor X` → engineer (codex) selesai. Lalu user
`/review` — reviewer dapat output engineer terakhir sebagai context.

Per-project, per-role last result. TTL 24 jam (lewat itu user retry from scratch).

Key: ``agent:ctx:proj:<project_id>:<role>``
Hash fields:
- agent      : agent name yang execute (codex/claude/glm)
- prompt     : prompt original (preview)
- summary    : summary dari job_done
- output     : full output (sampai 8KB; truncated kalau over)
- finished_at: ISO timestamp
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.adapters.redis_client import (
    LEGACY_AGENT_CTX_PATTERN,
    PROJECT_AGENT_CTX_PREFIX,
    get_client,
    k_agent_ctx_role,
)

logger = logging.getLogger(__name__)

CTX_TTL_SEC = 24 * 3600  # 24 hours
MAX_OUTPUT_BYTES = 8 * 1024  # 8KB cap

# Role-role yang dipakai untuk hand-off dalam flow standar. Dipakai oleh
# ``clear()`` untuk bulk delete saat user reset state project-nya.
KNOWN_ROLES: tuple[str, ...] = ("engineer", "reviewer", "architect")


async def store_result(
    project_id: str,
    role: str,
    *,
    agent: str,
    prompt: str,
    output: str,
    summary: str = "",
) -> None:
    """Simpan hasil agent untuk (project, role) — overwrite kalau sudah ada."""
    try:
        client = get_client()
        truncated = output[:MAX_OUTPUT_BYTES]
        await client.hset(k_agent_ctx_role(project_id, role), mapping={  # type: ignore[misc]
            "agent": agent,
            "prompt": prompt[:500],
            "summary": summary,
            "output": truncated,
            "truncated": "true" if len(output) > MAX_OUTPUT_BYTES else "false",
            "finished_at": datetime.now(UTC).isoformat(),
        })
        await client.expire(k_agent_ctx_role(project_id, role), CTX_TTL_SEC)
    except Exception as exc:
        logger.warning("agent_context store failed: %s", exc)


async def fetch_role(project_id: str, role: str) -> dict[str, Any] | None:
    """Ambil hasil terakhir (project, role)."""
    try:
        client = get_client()
        data = await client.hgetall(k_agent_ctx_role(project_id, role))  # type: ignore[misc]
        return dict(data) if data else None
    except Exception as exc:
        logger.warning("agent_context fetch failed: %s", exc)
        return None


def build_handoff_prefix(prev: dict[str, Any], current_role: str) -> str:
    """Format hasil sebelumnya jadi prefix untuk prompt agent berikutnya."""
    prev_agent = prev.get("agent", "?")
    prev_prompt = prev.get("prompt", "")
    output = prev.get("output", "")
    truncated = prev.get("truncated") == "true"
    suffix = " (truncated)" if truncated else ""
    return (
        f"Konteks dari run sebelumnya ({prev_agent}{suffix}):\n"
        f"Original prompt: {prev_prompt}\n"
        f"Output:\n```\n{output}\n```\n\n"
        f"Sebagai {current_role}, lanjutkan task berdasarkan konteks di atas:\n\n"
    )


async def clear(project_id: str, role: str | None = None) -> int:
    """Hapus context. Kalau role=None, hapus semua role yang dikenal."""
    try:
        client = get_client()
        if role:
            return int(await client.delete(k_agent_ctx_role(project_id, role)))
        n = 0
        for r in KNOWN_ROLES:
            n += int(await client.delete(k_agent_ctx_role(project_id, r)))
        return n
    except Exception as exc:
        logger.warning("agent_context clear failed: %s", exc)
        return 0


async def purge_legacy_keys() -> int:
    """Hapus semua key scratchpad legacy (sebelum project scoping).

    Legacy format: ``agent:ctx:<user_id>:<role>``  → di-purge.
    New format:    ``agent:ctx:proj:<project_id>:<role>`` → dipertahankan.

    Dipanggil sekali saat backend startup setelah deploy migrasi. Aman dipanggil
    berulang — idempotent, tidak akan hapus key baru.
    """
    try:
        client = get_client()
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = await client.scan(
                cursor=cursor,
                match=LEGACY_AGENT_CTX_PATTERN,
                count=200,
            )
            legacy = [k for k in keys if not k.startswith(PROJECT_AGENT_CTX_PREFIX)]
            if legacy:
                deleted += int(await client.delete(*legacy))
            if cursor == 0:
                break
        if deleted:
            logger.info("agent_context: purged %d legacy scratchpad keys", deleted)
        return deleted
    except Exception as exc:
        logger.warning("agent_context purge_legacy_keys failed: %s", exc)
        return 0
