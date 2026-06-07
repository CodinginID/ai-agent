"""Unit tests for TaskQueueAdapter — durable queue via Redis Streams (GAP-2).

Redis is replaced by an in-memory fake that models the parts of consumer-group
semantics we rely on: a stream of (id, fields), a pending entries list (PEL)
per group with idle timing, XACK removal, and XAUTOCLAIM re-delivery. This lets
us prove enqueue → consume → ack and the crash-recovery (reclaim) path without
a real Redis.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.adapters.task_queue import GROUP, TaskQueueAdapter


class FakeStreamRedis:
    """Minimal Redis-Streams fake: one stream, one group, a PEL with idle time."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, dict[str, str]]] = {}  # key -> {id: fields}
        self._seq = 0
        self._groups: dict[str, dict[str, str]] = {}  # key -> last-delivered cursor
        # PEL: key -> {id: idle_ms}. idle_ms is set explicitly by tests.
        self._pending: dict[str, dict[str, int]] = {}

    def _next_id(self) -> str:
        self._seq += 1
        return f"{self._seq}-0"

    async def xadd(
        self, key: str, fields: dict[str, str], maxlen: int = 0, approximate: bool = True
    ) -> str:
        entry_id = self._next_id()
        self._entries.setdefault(key, {})[entry_id] = dict(fields)
        return entry_id

    async def xgroup_create(
        self, key: str, group: str, id: str = "0", mkstream: bool = False
    ) -> bool:
        gkey = f"{key}:{group}"
        if gkey in self._groups:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        self._entries.setdefault(key, {})
        self._groups[gkey] = id
        self._pending.setdefault(key, {})
        return True

    async def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        count: int = 1,
        block: int | None = None,
    ) -> list[Any]:
        out: list[Any] = []
        for key in streams:
            entries = self._entries.get(key, {})
            pending = self._pending.setdefault(key, {})
            gkey = f"{key}:{group}"
            cursor = self._groups.get(gkey, "0")
            new: list[tuple[str, dict[str, str]]] = []
            for eid, fields in entries.items():
                if eid in pending:
                    continue
                if self._id_gt(eid, cursor):
                    new.append((eid, fields))
                if len(new) >= count:
                    break
            for eid, _ in new:
                pending[eid] = 0  # freshly delivered → idle 0
                self._groups[gkey] = eid
            if new:
                out.append((key, new))
        return out

    async def xack(self, key: str, group: str, message_id: str) -> int:
        pending = self._pending.get(key, {})
        return 1 if pending.pop(message_id, None) is not None else 0

    async def xautoclaim(
        self,
        key: str,
        group: str,
        consumer: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: int = 10,
    ) -> tuple[str, list[Any], list[str]]:
        pending = self._pending.get(key, {})
        entries = self._entries.get(key, {})
        claimed: list[tuple[str, dict[str, str] | None]] = []
        for eid, idle in sorted(pending.items()):
            if idle >= min_idle_time:
                claimed.append((eid, entries.get(eid)))
                pending[eid] = 0  # claimed → idle resets
            if len(claimed) >= count:
                break
        return "0-0", claimed, []

    @staticmethod
    def _id_gt(a: str, b: str) -> bool:
        return int(a.split("-")[0]) > int(b.split("-")[0])

    # Test helper: simulate time passing for delivered-but-unacked messages.
    def age_pending(self, key: str, idle_ms: int) -> None:
        for eid in self._pending.get(key, {}):
            self._pending[key][eid] = idle_ms


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeStreamRedis:
    f = FakeStreamRedis()
    monkeypatch.setattr("app.adapters.task_queue.get_client", lambda: f)
    return f


@pytest.fixture
def queue() -> TaskQueueAdapter:
    return TaskQueueAdapter(user_id="u1", consumer_name="backend-a")


# ── enqueue → consume → ack ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_returns_message_id(fake: FakeStreamRedis, queue: TaskQueueAdapter) -> None:
    mid = await queue.enqueue({"step": "1", "desc": "do thing"})
    assert mid
    assert "-" in mid


@pytest.mark.asyncio
async def test_consume_returns_enqueued_step(
    fake: FakeStreamRedis, queue: TaskQueueAdapter
) -> None:
    await queue.enqueue({"step": "1", "desc": "build"})

    steps = await queue.consume(count=10)

    assert len(steps) == 1
    assert steps[0].fields == {"step": "1", "desc": "build"}
    assert steps[0].delivery_count == 1


@pytest.mark.asyncio
async def test_consume_respects_count(fake: FakeStreamRedis, queue: TaskQueueAdapter) -> None:
    for i in range(5):
        await queue.enqueue({"step": str(i)})

    first = await queue.consume(count=2)
    assert len(first) == 2

    rest = await queue.consume(count=10)
    assert len(rest) == 3


@pytest.mark.asyncio
async def test_consumed_messages_not_redelivered_until_acked(
    fake: FakeStreamRedis, queue: TaskQueueAdapter
) -> None:
    await queue.enqueue({"step": "1"})
    await queue.consume(count=10)

    # Already in PEL (delivered, unacked) → a fresh ">" read sees nothing new.
    again = await queue.consume(count=10)
    assert again == []


@pytest.mark.asyncio
async def test_ack_removes_from_pending(fake: FakeStreamRedis, queue: TaskQueueAdapter) -> None:
    await queue.enqueue({"step": "1"})
    steps = await queue.consume(count=10)
    await queue.ack(steps[0].message_id)

    # Nothing left pending → reclaim finds nothing even at idle 0.
    fake.age_pending(queue._key, 999_999)
    reclaimed = await queue.reclaim(min_idle_ms=1)
    assert reclaimed == []


# ── crash recovery: reclaim ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reclaim_redelivers_stale_pending(
    fake: FakeStreamRedis, queue: TaskQueueAdapter
) -> None:
    await queue.enqueue({"step": "1", "desc": "half done"})
    await queue.consume(count=10)  # delivered but never acked (simulated crash)

    fake.age_pending(queue._key, 60_000)  # 60s idle

    reclaimed = await queue.reclaim(min_idle_ms=30_000)

    assert len(reclaimed) == 1
    assert reclaimed[0].fields == {"step": "1", "desc": "half done"}
    assert reclaimed[0].delivery_count == 2  # marks it as a redelivery


@pytest.mark.asyncio
async def test_reclaim_ignores_fresh_pending(
    fake: FakeStreamRedis, queue: TaskQueueAdapter
) -> None:
    await queue.enqueue({"step": "1"})
    await queue.consume(count=10)  # idle 0

    reclaimed = await queue.reclaim(min_idle_ms=30_000)
    assert reclaimed == []


@pytest.mark.asyncio
async def test_consume_creates_group_idempotently(
    fake: FakeStreamRedis, queue: TaskQueueAdapter
) -> None:
    # Two consumes in a row must not raise on BUSYGROUP.
    await queue.enqueue({"step": "1"})
    await queue.consume(count=1)
    await queue.enqueue({"step": "2"})
    second = await queue.consume(count=10)
    assert len(second) == 1


@pytest.mark.asyncio
async def test_empty_queue_consume_returns_empty(
    fake: FakeStreamRedis, queue: TaskQueueAdapter
) -> None:
    assert await queue.consume(count=10) == []


@pytest.mark.asyncio
async def test_group_constant_used(fake: FakeStreamRedis, queue: TaskQueueAdapter) -> None:
    await queue.enqueue({"step": "1"})
    await queue.consume(count=1)
    assert f"{queue._key}:{GROUP}" in fake._groups
