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
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse, StreamingResponse

from app.composition import build_roster
from app.interfaces.chat import _resolve_caller
from app.ports.push import NullPush, PushMessage, PushPort
from app.ports.roster import DEFAULT_ROSTER

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/room", tags=["room"])


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

# Role worker (backend) → Role kartu kanban di frontend (types.ts).
_ROLE_CARD: dict[str, str] = {
    "engineer": "coder",
    "infra": "deployer",
    "reviewer": "reviewer",
    "research": "researcher",
}


class RoomTaskObserver:
    """TaskObserver → RoomBus: bikin gather-room hidup saat TaskRunner jalan.

    Publish ``activity`` (feed) + ``agent.status`` (avatar) per fase task, lalu
    delegasi ke ``inner`` (LoggingTaskObserver) supaya papan ``/tasks`` & log
    tetap terisi. Best-effort — kegagalan publish tak boleh menggagalkan task.

    ``push`` (opsional) mengirim notifikasi Web Push ke user saat task selesai
    (mis. HP terkunci / tab tidak aktif) — ingat ``task_id -> user_id`` dari
    ``task_started`` lalu dipakai & dibuang di ``task_finished``.
    """

    def __init__(self, inner: Any, push: PushPort | None = None) -> None:
        self._inner = inner
        self._push = push if push is not None else NullPush()
        self._task_users: dict[str, str] = {}

    @staticmethod
    def _avatar(role: str) -> str:
        return _ROLE_AVATAR.get(role, "yusuf")

    @staticmethod
    def _card_id(task_id: str, order: int) -> str:
        return f"{task_id}-{order}"

    def task_started(self, task_id: str, user_id: str, request: str) -> None:
        self._task_users[task_id] = user_id
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
            "task.card",
            id=self._card_id(task_id, order),
            desc=description[:100],
            role=_ROLE_CARD.get(role, "researcher"),
            col="doing",
        )
        publish_room_event(
            "activity", level="info",
            text=f"Langkah {order} → {role}: {description[:100]}",
        )
        self._inner.step_started(task_id, order, role, description)

    def step_finished(self, task_id: str, order: int, role: str, ok: bool, detail: str) -> None:
        avatar = self._avatar(role)
        publish_room_event("agent.status", id=avatar, status="idle")
        publish_room_event(
            "task.card",
            id=self._card_id(task_id, order),
            col="done" if ok else "todo",
        )
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
        user_id = self._task_users.pop(task_id, None)
        if user_id is not None:
            self._notify_task_result(user_id, task_id, ok=ok, note=note)
        self._inner.task_finished(task_id, closed=closed, ok=ok, note=note)

    def _notify_task_result(self, user_id: str, task_id: str, *, ok: bool, note: str) -> None:
        """Kirim Web Push best-effort — fire-and-forget supaya tak menahan caller.

        ``task_finished`` bagian Protocol sync, sedangkan ``PushPort.notify``
        async — dijadwalkan sebagai task di event loop yang sedang jalan (task
        runner selalu dipanggil dari ``async def run``). Tanpa loop aktif
        (mis. dipanggil dari kode sync murni), push dilewati diam-diam.
        """
        msg = PushMessage(
            title="Octopus",
            body=f"Tugas {'selesai' if ok else 'berhenti'}: {note[:120]}",
            tag=f"task-{task_id}",
            kind="task",
            url="/",
        )

        async def _send() -> None:
            try:
                await self._push.notify(user_id, msg)
            except Exception:
                logger.debug("push task_finished gagal", exc_info=True)

        try:
            asyncio.get_running_loop().create_task(_send())
        except RuntimeError:
            logger.debug("push task_finished dilewati: tidak ada event loop aktif")


def _default_agent_dicts() -> list[dict[str, str]]:
    return [{"id": a.id, "name": a.name, "role": a.role} for a in DEFAULT_ROSTER]


def _snapshot(agents: list[dict[str, str]], workers: int = 0) -> dict[str, Any]:
    return {
        "type": "room.snapshot",
        "agents": [dict(a, status="idle") for a in agents],
        "tasks": [],
        "approvals": [],
        "workers": workers,
    }


async def _worker_count_for(user_id: str, mode: str) -> int:
    """Hitung pasukan online untuk room caller. Admin → user demo (room tunggal)."""
    from app.adapters.worker_registry import worker_count
    from app.interfaces.chat import _resolve_admin_target

    target = user_id
    if mode == "admin":
        try:
            target = _resolve_admin_target("demo@local")
        except Exception:
            return 0
    try:
        return await worker_count(target)
    except Exception:
        return 0


async def _agents_snapshot_for(user_id: str, mode: str) -> list[dict[str, str]]:
    """Ambil roster (nama/peran hasil CRUD user) untuk room caller.

    Admin → resolve ke user demo (room tunggal), sama seperti
    ``_worker_count_for``. Gagal di titik mana pun (resolve/Redis) → fallback
    ke roster default supaya ruangan tetap tampil.
    """
    target = user_id
    if mode == "admin":
        from app.interfaces.chat import _resolve_admin_target

        try:
            target = _resolve_admin_target("demo@local")
        except Exception:
            return _default_agent_dicts()
    try:
        agents = await build_roster().list(target)
        return [{"id": a.id, "name": a.name, "role": a.role} for a in agents]
    except Exception:
        return _default_agent_dicts()


def _sse(event: dict[str, Any]) -> str:
    etype = event.get("type", "message")
    return f"event: {etype}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/state")
async def room_state(authorization: str | None = Header(default=None)) -> JSONResponse:
    user_id, mode = _resolve_caller(authorization)  # gate: 401 kalau token invalid
    workers = await _worker_count_for(user_id, mode)
    agents = await _agents_snapshot_for(user_id, mode)
    return JSONResponse(_snapshot(agents, workers))


async def _room_stream(agents: list[dict[str, str]], workers: int = 0) -> AsyncIterator[str]:
    q = _bus.subscribe()
    try:
        yield _sse(_snapshot(agents, workers))
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
    user_id, mode = _resolve_caller(authorization)
    workers = await _worker_count_for(user_id, mode)
    agents = await _agents_snapshot_for(user_id, mode)
    return StreamingResponse(_room_stream(agents, workers), media_type="text/event-stream")
