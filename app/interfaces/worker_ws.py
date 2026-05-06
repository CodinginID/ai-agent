"""WebSocket endpoint untuk worker (TUI di mesin user).

Worker connect dengan Bearer session token via query param. Backend:

1. Validate token → resolve user_id
2. Register worker_id di Redis (presence)
3. Simpan WS object di ``_connections[(user_id, worker_id)]`` (in-process)
4. Loop: terima pesan worker (heartbeat, job_chunk, job_done)
5. Saat WS close: unregister, remove dari connections

Backend dispatcher (Fase B2) akan lookup worker dari ``_connections`` lalu
``await ws.send_json({"type": "job", ...})``.

Catatan single-instance: connection map ada di process memory backend ini.
Untuk multi-instance backend nanti, perlu Redis pub/sub untuk cross-instance
routing — tidak relevan sekarang karena baru satu replica.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import secrets
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.adapters.sessions import UserSessionRepository
from app.adapters.worker_registry import (
    heartbeat,
    register,
    unregister,
)
from app.composition import _session_factory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["worker"])

# Connection map: (user_id, worker_id) → WebSocket. In-process satu backend.
_connections: dict[tuple[str, str], WebSocket] = {}
_connections_lock = asyncio.Lock()

# Job correlation: job_id → asyncio.Queue. Dispatcher push job ke worker via WS,
# WS handler nge-route balasan worker (job_chunk/job_done/job_error) ke queue
# yang sedang di-await dispatcher.
_pending_jobs: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_pending_jobs_lock = asyncio.Lock()

# Concurrency limit per worker: cegah Codex/Claude paralel berlebihan di mesin
# user (CPU/RAM bisa kepukul). Default 1 (sequential), override via env
# ``WORKER_CONCURRENCY``. Future: per-user override di DB.
_worker_semaphores: dict[str, asyncio.Semaphore] = {}
_worker_semaphores_lock = asyncio.Lock()


async def _get_worker_semaphore(worker_id: str) -> asyncio.Semaphore:
    async with _worker_semaphores_lock:
        sem = _worker_semaphores.get(worker_id)
        if sem is None:
            from app.config import settings as _settings
            sem = asyncio.Semaphore(_settings.worker_concurrency)
            _worker_semaphores[worker_id] = sem
        return sem


# ── Multi-instance routing (B5g) ─────────────────────────────────────────────
# Worker biasa ke-WS-connect ke salah satu backend instance. Tapi job mungkin
# dispatched dari instance lain. Solusi: backend simpan ``originator_instance``
# di Redis hash job:<id>; ketika reply datang dari worker, cek originator —
# kalau bukan kita, PUBLISH ke ``backend:<originator>``. Originator subscribe
# ke channel itu dan routing ke local _pending_jobs.

_pubsub_task: asyncio.Task[None] | None = None


async def _route_reply_to_local_queue(msg: dict[str, Any]) -> None:
    """Router untuk reply yang datang via WS atau pub/sub."""
    job_id = str(msg.get("job_id", ""))
    if not job_id:
        return
    async with _pending_jobs_lock:
        queue = _pending_jobs.get(job_id)
    if queue is not None:
        await queue.put(msg)


async def _route_or_forward_reply(msg: dict[str, Any]) -> None:
    """Route reply ke local queue atau forward ke originator instance."""
    from app.adapters import job_store
    from app.adapters.redis_client import get_client, k_backend_channel
    from app.config import settings as _settings

    job_id = str(msg.get("job_id", ""))
    if not job_id:
        return

    job_data = await job_store.get(job_id)
    originator = (job_data or {}).get("originator_instance", "")

    if not originator or originator == _settings.instance_id:
        # Job punya kita — route lokal.
        await _route_reply_to_local_queue(msg)
        return

    # Job punya instance lain — forward via pub/sub.
    try:
        client = get_client()
        await client.publish(k_backend_channel(originator), json.dumps(msg))
        logger.debug("forwarded reply for job %s to instance %s", job_id, originator)
    except Exception:
        logger.exception("failed to forward reply via pubsub")


async def _pubsub_listener_loop() -> None:
    """Subscribe ke channel kita sendiri, route incoming reply ke local queue."""
    from app.adapters.redis_client import get_client, k_backend_channel
    from app.config import settings as _settings

    client = get_client()
    pubsub = client.pubsub()
    channel = k_backend_channel(_settings.instance_id)
    await pubsub.subscribe(channel)
    logger.info("pubsub listener started: channel=%s", channel)

    try:
        async for raw_msg in pubsub.listen():
            if raw_msg.get("type") != "message":
                continue
            data = raw_msg.get("data")
            if not data:
                continue
            try:
                payload = json.loads(data) if isinstance(data, str) else json.loads(data.decode())
            except Exception:
                continue
            await _route_reply_to_local_queue(payload)
    except asyncio.CancelledError:
        pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:
            pass


async def start_pubsub_listener() -> None:
    """Dipanggil dari gateway lifespan startup."""
    global _pubsub_task
    if _pubsub_task is None or _pubsub_task.done():
        _pubsub_task = asyncio.create_task(_pubsub_listener_loop())


async def stop_pubsub_listener() -> None:
    global _pubsub_task
    if _pubsub_task is not None:
        _pubsub_task.cancel()
        try:
            await _pubsub_task
        except asyncio.CancelledError:
            pass
        _pubsub_task = None


class NoWorkerAvailableError(Exception):
    """User-id tidak punya worker online."""


class JobTimeoutError(Exception):
    """Worker tidak balas dalam batas waktu."""


async def _resolve_session(token: str) -> str | None:
    """Validate session token via existing UserSessionRepository."""
    if not token:
        return None
    repo = UserSessionRepository(_session_factory())
    info = repo.resolve(token)
    return info.user_id if info else None


@router.websocket("/worker")
async def worker_socket(
    websocket: WebSocket,
    session: str = Query(..., description="Bearer session token"),
) -> None:
    """Worker WebSocket — auth via ``?session=<token>``."""
    user_id = await _resolve_session(session)
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid session")
        return

    worker_id = secrets.token_urlsafe(8)
    await websocket.accept()
    logger.info("worker connected: user_id=%s worker_id=%s", user_id, worker_id)

    try:
        await register(user_id, worker_id, metadata={
            "user_agent": websocket.headers.get("user-agent", "unknown"),
            "client_host": websocket.client.host if websocket.client else "unknown",
        })
    except Exception as exc:
        logger.exception("failed to register worker in Redis")
        await websocket.send_json({"type": "error", "message": f"registry: {exc}"})
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    async with _connections_lock:
        _connections[(user_id, worker_id)] = websocket

    # Send greeting agar worker tahu register sukses
    await websocket.send_json({
        "type": "registered",
        "worker_id": worker_id,
        "user_id": user_id,
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid JSON"})
                continue

            kind = msg.get("type", "")
            if kind == "heartbeat":
                await heartbeat(user_id, worker_id)
                await websocket.send_json({"type": "heartbeat_ack"})
            elif kind == "capabilities":
                # Worker advertise CLI binary yang terinstall.
                from app.adapters.redis_client import get_client, k_caps
                from app.adapters.worker_registry import WORKER_TTL_SEC
                agents_caps = msg.get("agents", {}) or {}
                client = get_client()
                pipe = client.pipeline()
                for aid, info in agents_caps.items():
                    if not isinstance(info, dict):
                        continue
                    if info.get("installed"):
                        pipe.sadd(k_caps(user_id, aid), worker_id)
                        pipe.expire(k_caps(user_id, aid), WORKER_TTL_SEC * 5)
                    else:
                        pipe.srem(k_caps(user_id, aid), worker_id)
                await pipe.execute()
                logger.debug("worker %s capabilities: %s", worker_id, list(agents_caps))
            elif kind in ("job_chunk", "job_done", "job_error"):
                if not msg.get("job_id"):
                    logger.warning("worker %s sent %s without job_id", worker_id, kind)
                    continue
                # Multi-instance routing: kalau originator instance bukan kita,
                # forward via Redis pub/sub.
                await _route_or_forward_reply(msg)
            else:
                logger.debug("unknown msg type from %s: %s", worker_id, kind)

    except WebSocketDisconnect:
        logger.info("worker disconnected: user_id=%s worker_id=%s", user_id, worker_id)
    except Exception:
        logger.exception("worker socket error")
    finally:
        async with _connections_lock:
            _connections.pop((user_id, worker_id), None)
        try:
            await unregister(user_id, worker_id)
        except Exception:
            logger.exception("failed to unregister worker")


# ── Public helpers untuk dispatcher (Fase B2) ─────────────────────────────────

async def get_worker_socket(user_id: str, worker_id: str) -> WebSocket | None:
    async with _connections_lock:
        return _connections.get((user_id, worker_id))


async def list_user_worker_ids(user_id: str) -> list[str]:
    """Lookup in-process — beda dengan worker_registry yang Redis-backed.

    In-process: cuma worker yang konek ke backend instance INI.
    Redis registry: cross-instance.
    Untuk single-instance saat ini, dua-duanya identik.
    """
    async with _connections_lock:
        return [w for (u, w) in _connections if u == user_id]


async def _pick_worker(user_id: str) -> tuple[str, WebSocket]:
    """Pilih satu worker random untuk user. Raise kalau tidak ada."""
    async with _connections_lock:
        candidates = [
            (worker_id, ws) for (uid, worker_id), ws in _connections.items()
            if uid == user_id
        ]
    if not candidates:
        raise NoWorkerAvailableError(
            f"user {user_id} tidak punya worker online. Buka TUI di mesin user."
        )
    return random.choice(candidates)


async def dispatch_agent_job(
    user_id: str,
    agent: str,
    prompt: str,
    *,
    timeout_sec: float = 300.0,
    extra: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Dispatch job ke worker user, yield event sampai job_done/job_error.

    Caller (chat handler) tinggal::

        async for event in dispatch_agent_job(user_id, "codex", "refactor X"):
            if event["type"] == "job_chunk":
                ...stream chunk["text"]...
            elif event["type"] == "job_done":
                ...final summary...

    Raise:
        ``NoWorkerAvailableError`` kalau tidak ada worker online.
        ``JobTimeoutError`` kalau worker idle > timeout_sec.
    """
    worker_id, ws = await _pick_worker(user_id)
    sem = await _get_worker_semaphore(worker_id)

    # Kalau slot full, beritahu caller "queued" — biar UI bisa tampilin pesan
    # "tunggu, ada job lain yang lagi jalan", dibanding diam saja.
    if sem.locked():
        yield {
            "type": "job_queued",
            "worker_id": worker_id,
            "agent": agent,
            "message": (
                f"worker {worker_id[:8]}… sedang sibuk (concurrency limit), "
                "queued — akan jalan saat slot bebas"
            ),
        }

    async with sem:
        from app.adapters import agent_context, job_store
        from app.config import settings as _settings

        job_id = secrets.token_urlsafe(12)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async with _pending_jobs_lock:
            _pending_jobs[job_id] = queue

        # Persist job state ke Redis — survive restart, observability, multi-instance
        await job_store.create(
            job_id,
            user_id=user_id,
            worker_id=worker_id,
            agent=agent,
            prompt=prompt,
            originator_instance=_settings.instance_id,
        )

        try:
            payload: dict[str, Any] = {
                "type": "job",
                "job_id": job_id,
                "agent": agent,
                "prompt": prompt,
            }
            if extra:
                payload["extra"] = extra
            try:
                await ws.send_json(payload)
            except Exception as exc:
                await job_store.update_status(job_id, "error", error=f"send failed: {exc}")
                yield {"type": "job_error", "job_id": job_id, "message": f"send failed: {exc}"}
                return

            await job_store.update_status(job_id, "running")
            yield {"type": "job_started", "job_id": job_id, "worker_id": worker_id, "agent": agent}

            # Akumulasi output chunks untuk shared context (B5f) — biar role
            # berikutnya bisa hand-off dapat output sebelumnya.
            output_buf: list[str] = []
            role = (extra or {}).get("role", "")

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=timeout_sec)
                except asyncio.TimeoutError:
                    await job_store.update_status(
                        job_id, "error",
                        error=f"timeout {timeout_sec:.0f}s — worker tidak balas",
                    )
                    yield {
                        "type": "job_error",
                        "job_id": job_id,
                        "message": f"timeout {timeout_sec:.0f}s — worker tidak balas",
                    }
                    return
                yield event
                kind = event.get("type", "")
                if kind == "job_chunk":
                    output_buf.append(str(event.get("text", "")))
                elif kind == "job_done":
                    summary = str(event.get("summary", ""))
                    await job_store.update_status(job_id, "done", summary=summary)
                    if role:
                        await agent_context.store_result(
                            user_id, role,
                            agent=agent,
                            prompt=prompt,
                            output="".join(output_buf).strip(),
                            summary=summary,
                        )
                    return
                elif kind == "job_error":
                    await job_store.update_status(
                        job_id, "error", error=str(event.get("message", "")),
                    )
                    return
        finally:
            async with _pending_jobs_lock:
                _pending_jobs.pop(job_id, None)
