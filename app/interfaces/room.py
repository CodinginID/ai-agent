"""Room interface — read-model gather-room untuk frontend (Fase 3 P2).

- ``GET /room/state``  : snapshot roster pasukan + tugas + approval (JSON).
- ``GET /room/stream`` : SSE — kirim snapshot lalu event live (RoomBus) + heartbeat.

``RoomBus`` = pub/sub in-process (asyncio). Producer (chat/orchestrator) memanggil
``publish_room_event(...)`` untuk mendorong event ke semua klien yang tersambung.
Multi-instance nanti pakai Redis pub/sub (Fase deploy).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse, StreamingResponse

from app.interfaces.chat import _resolve_caller

router = APIRouter(prefix="/room", tags=["room"])

# Cast tetap ruangan (selaras mockup). Presence worker real menyusul.
_ROSTER: tuple[dict[str, str], ...] = (
    {"id": "octo", "name": "Octo", "role": "manager"},
    {"id": "nadia", "name": "Nadia", "role": "coder"},
    {"id": "bima", "name": "Bima", "role": "coder"},
    {"id": "sari", "name": "Sari", "role": "tester"},
    {"id": "rangga", "name": "Rangga", "role": "reviewer"},
    {"id": "dewi", "name": "Dewi", "role": "deployer"},
    {"id": "yusuf", "name": "Yusuf", "role": "researcher"},
)


class RoomBus:
    """Pub/sub in-process untuk event ruangan (satu instance)."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        for q in list(self._subs):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)


_bus = RoomBus()


def publish_room_event(event_type: str, **data: Any) -> None:
    """API publik untuk producer mendorong event ke ruangan (semua klien SSE)."""
    _bus.publish({"type": event_type, **data})


# Role worker (TaskRunner) → avatar roster yang mewakili di ruangan.
_ROLE_AVATAR: dict[str, str] = {
    "engineer": "nadia",
    "infra": "dewi",
    "reviewer": "rangga",
    "research": "yusuf",
}


class RoomTaskObserver:
    """TaskObserver → RoomBus: bikin gather-room hidup saat TaskRunner jalan.

    Publish ``activity`` (feed) + ``agent.status`` (avatar) per fase task, lalu
    delegasi ke ``inner`` (LoggingTaskObserver) supaya papan ``/tasks`` & log
    tetap terisi. Best-effort — kegagalan publish tak boleh menggagalkan task.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    @staticmethod
    def _avatar(role: str) -> str:
        return _ROLE_AVATAR.get(role, "yusuf")

    def task_started(self, task_id: str, user_id: str, request: str) -> None:
        publish_room_event("agent.status", id="octo", status="working")
        publish_room_event("activity", level="info", text=f"Octo memecah tugas: {request[:120]}")
        self._inner.task_started(task_id, user_id, request)

    def issue_opened(self, task_id: str, issue_number: int, issue_url: str) -> None:
        publish_room_event("activity", level="info", text=f"Tugas dicatat (#{issue_number})")
        self._inner.issue_opened(task_id, issue_number, issue_url)

    def step_started(self, task_id: str, order: int, role: str, description: str) -> None:
        avatar = self._avatar(role)
        publish_room_event("agent.status", id=avatar, status="working")
        publish_room_event(
            "activity", level="info",
            text=f"Langkah {order} → {role}: {description[:100]}",
        )
        self._inner.step_started(task_id, order, role, description)

    def step_finished(self, task_id: str, order: int, role: str, ok: bool, detail: str) -> None:
        avatar = self._avatar(role)
        publish_room_event("agent.status", id=avatar, status="idle")
        publish_room_event(
            "activity",
            level="done" if ok else "error",
            text=f"Langkah {order} ({role}) {'selesai' if ok else 'gagal'}",
        )
        self._inner.step_finished(task_id, order, role, ok, detail)

    def task_finished(self, task_id: str, *, closed: bool, ok: bool, note: str) -> None:
        publish_room_event("agent.status", id="octo", status="idle")
        publish_room_event(
            "activity",
            level="done" if ok else "error",
            text=f"Tugas {'selesai' if ok else 'berhenti'}: {note[:120]}",
        )
        self._inner.task_finished(task_id, closed=closed, ok=ok, note=note)


def _snapshot() -> dict[str, Any]:
    return {
        "type": "room.snapshot",
        "agents": [dict(a, status="idle") for a in _ROSTER],
        "tasks": [],
        "approvals": [],
    }


def _sse(event: dict[str, Any]) -> str:
    etype = event.get("type", "message")
    return f"event: {etype}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/state")
async def room_state(authorization: str | None = Header(default=None)) -> JSONResponse:
    _resolve_caller(authorization)  # gate: session/admin token (401 kalau tidak)
    return JSONResponse(_snapshot())


async def _room_stream() -> AsyncIterator[str]:
    q = _bus.subscribe()
    try:
        yield _sse(_snapshot())
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=15.0)
                yield _sse(event)
            except TimeoutError:
                yield ": heartbeat\n\n"  # keep-alive SSE comment
    finally:
        _bus.unsubscribe(q)


@router.get("/stream")
async def room_stream(
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    _resolve_caller(authorization)
    return StreamingResponse(_room_stream(), media_type="text/event-stream")
