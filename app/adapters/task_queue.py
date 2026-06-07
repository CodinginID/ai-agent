"""Durable task queue via Redis Streams (GAP-2).

Why Streams (not a plain list / BRPOP): a consumer group gives us a *pending
entries list* (PEL). When a message is read it stays pending until acked, so if
the backend crashes mid-step the message is not lost — a later ``reclaim`` picks
up anything idle beyond a threshold and re-delivers it. That is the resume-after-
restart property the orchestrator needs and an in-process loop cannot provide.

No Celery/RQ: Redis is already in the swarm stack, and Streams cover enqueue,
at-least-once delivery, ack, and crash recovery on their own.

State per message:
    enqueued (XADD) → delivered (XREADGROUP, now in PEL) → acked (XACK, leaves PEL)
                                                        ↘ idle too long → reclaimed

Implements ``app.ports.task_queue.TaskQueuePort``. Hexagonal: the orchestrator
depends on the port; only ``main``/composition wires this concrete adapter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

from app.adapters.redis_client import get_client, k_task_stream
from app.ports.task_queue import QueuedStep

logger = logging.getLogger(__name__)

GROUP = "dispatchers"
# Cap stream growth — acked entries are trimmed approximately, far above the
# expected in-flight depth so we never drop an un-consumed step.
_MAXLEN = 10_000


def _decode(value: Any) -> str:
    """Redis may return bytes or str depending on client decode settings."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _decode_fields(raw: dict[Any, Any]) -> dict[str, str]:
    return {_decode(k): _decode(v) for k, v in raw.items()}


@dataclass
class TaskQueueAdapter:
    """Per-user durable step queue. One stream + one shared consumer group;
    each backend instance is a distinct consumer (``consumer_name``)."""

    user_id: str
    consumer_name: str

    @property
    def _key(self) -> str:
        return k_task_stream(self.user_id)

    async def _ensure_group(self) -> None:
        """Create the consumer group idempotently (mkstream so the stream exists
        even before the first enqueue). Swallow BUSYGROUP — already created."""
        client = get_client()
        try:
            await client.xgroup_create(
                self._key, GROUP, id="0", mkstream=True,
            )
        except Exception as exc:  # redis.ResponseError: BUSYGROUP
            if "BUSYGROUP" not in str(exc):
                raise

    async def enqueue(self, fields: dict[str, str]) -> str:
        client = get_client()
        # redis-py's stub types the field mapping invariantly over a broad
        # bytes|str|int|float union; our str→str payload is a valid subset.
        message_id = await client.xadd(
            self._key,
            cast("dict[Any, Any]", fields),
            maxlen=_MAXLEN,
            approximate=True,
        )
        return _decode(message_id)

    async def consume(self, count: int = 1, block_ms: int = 0) -> list[QueuedStep]:
        await self._ensure_group()
        client = get_client()
        # ">" = only messages never delivered to any consumer in this group.
        resp = await client.xreadgroup(
            GROUP,
            self.consumer_name,
            {self._key: ">"},
            count=count,
            block=block_ms or None,
        )
        return self._flatten(resp)

    async def ack(self, message_id: str) -> None:
        client = get_client()
        await client.xack(self._key, GROUP, message_id)

    async def reclaim(self, min_idle_ms: int, count: int = 10) -> list[QueuedStep]:
        """Re-claim messages idle longer than ``min_idle_ms`` — the crash-recovery
        path. Uses XAUTOCLAIM (Redis 6.2+) to transfer ownership of stale pending
        entries to this consumer and return them for re-processing."""
        await self._ensure_group()
        client = get_client()
        # XAUTOCLAIM returns (next_cursor, claimed_entries, deleted_ids).
        result = await client.xautoclaim(
            self._key,
            GROUP,
            self.consumer_name,
            min_idle_time=min_idle_ms,
            start_id="0-0",
            count=count,
        )
        entries = result[1] if len(result) >= 2 else []
        return self._to_steps(entries, reclaimed=True)

    def _flatten(self, resp: Any) -> list[QueuedStep]:
        """XREADGROUP returns [(stream_key, [(id, fields), ...])]."""
        if not resp:
            return []
        steps: list[QueuedStep] = []
        for _stream, entries in resp:
            steps.extend(self._to_steps(entries, reclaimed=False))
        return steps

    def _to_steps(self, entries: Any, *, reclaimed: bool) -> list[QueuedStep]:
        steps: list[QueuedStep] = []
        for entry_id, raw_fields in entries or []:
            if raw_fields is None:
                # XAUTOCLAIM can surface ids whose payload was trimmed/deleted;
                # nothing to process, but the id should still be ackable.
                continue
            steps.append(
                QueuedStep(
                    message_id=_decode(entry_id),
                    fields=_decode_fields(raw_fields),
                    delivery_count=2 if reclaimed else 1,
                )
            )
        return steps
