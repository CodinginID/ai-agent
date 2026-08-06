"""Port for a durable task queue — survives backend restart (GAP-2).

The orchestrator enqueues task steps as messages on a stream; a consumer
(the dispatcher) reads them in a consumer group, processes each, and acks on
success. Messages that were delivered but never acked (the backend crashed
mid-step) can be re-claimed and re-delivered — that is the durability guarantee
an in-process loop cannot give.

Depending on a Protocol (not the concrete ``TaskQueueAdapter``) keeps the
orchestrator hexagonal-clean and testable with an in-memory fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class QueuedStep:
    """One delivered queue message.

    ``message_id`` is the stream entry id used to ack/claim. ``fields`` is the
    decoded payload (str→str) the consumer needs to dispatch the step.
    ``delivery_count`` is how many times this message has been delivered — >1
    means it was re-claimed after a crash, so the consumer can decide to give
    up after N attempts instead of looping forever.
    """

    message_id: str
    fields: dict[str, str] = field(default_factory=dict)
    delivery_count: int = 1


class TaskQueuePort(Protocol):
    async def enqueue(self, fields: dict[str, str]) -> str:
        """Append a step to the queue. Returns the stream message id."""
        ...

    async def consume(
        self, count: int = 1, block_ms: int = 0,
    ) -> list[QueuedStep]:
        """Read up to ``count`` new messages for this consumer (XREADGROUP)."""
        ...

    async def ack(self, message_id: str) -> None:
        """Acknowledge a processed message so it leaves the pending list."""
        ...

    async def reclaim(
        self, min_idle_ms: int, count: int = 10,
    ) -> list[QueuedStep]:
        """Re-claim messages idle longer than ``min_idle_ms`` (crash recovery)."""
        ...
