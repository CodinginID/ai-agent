#!/usr/bin/env python3
"""Worker uji minimal — pasukan tiruan untuk E2E testing dispatch.

Bicara protokol WS worker (`/ws/worker`): register → capabilities → heartbeat,
lalu balas setiap `job` dengan `job_chunk` + `job_done` (echo, tanpa CLI asli).

Env:
    WORKER_WS_URL   default ws://aiagent_web/ws/worker
    WORKER_SESSION  session token (wajib)
    WORKER_DEVICE   nama device tampil di roster (default test-worker)
    WORKER_AGENTS   comma list agent yang "installed" (default codex,claude,glm)
"""
from __future__ import annotations

import asyncio
import json
import os

import websockets

WS_URL = os.environ.get("WORKER_WS_URL", "ws://aiagent_web/ws/worker")
SESSION = os.environ.get("WORKER_SESSION", "")
DEVICE = os.environ.get("WORKER_DEVICE", "test-worker")
AGENTS = [a.strip() for a in os.environ.get("WORKER_AGENTS", "codex,claude,glm").split(",") if a.strip()]


async def _heartbeat(ws: websockets.WebSocketClientProtocol) -> None:
    while True:
        await asyncio.sleep(20)
        await ws.send(json.dumps({"type": "heartbeat"}))


async def _handle_job(ws: websockets.WebSocketClientProtocol, msg: dict) -> None:
    job_id = msg.get("job_id", "")
    agent = msg.get("agent", "?")
    prompt = msg.get("prompt", "")
    print(f"[job] {job_id} agent={agent} prompt={prompt[:80]!r}", flush=True)
    await ws.send(json.dumps({
        "type": "job_chunk",
        "job_id": job_id,
        "text": f"[{DEVICE}/{agent}] menerima tugas: {prompt[:120]}\n",
    }))
    await asyncio.sleep(0.5)
    await ws.send(json.dumps({
        "type": "job_done",
        "job_id": job_id,
        "summary": f"selesai (mock worker) oleh {agent} di {DEVICE}",
    }))
    print(f"[job] {job_id} done", flush=True)


async def _session_once() -> None:
    url = f"{WS_URL}?session={SESSION}"
    async with websockets.connect(url, max_size=None) as ws:
        hb = asyncio.create_task(_heartbeat(ws))
        await ws.send(json.dumps({
            "type": "capabilities",
            "device_name": DEVICE,
            "agents": {a: {"installed": True} for a in AGENTS},
        }))
        try:
            async for raw in ws:
                msg = json.loads(raw)
                kind = msg.get("type", "")
                if kind == "registered":
                    print(f"[worker] registered worker_id={msg.get('worker_id')}", flush=True)
                elif kind == "job":
                    await _handle_job(ws, msg)
                elif kind == "heartbeat_ack":
                    pass
                else:
                    print(f"[worker] <- {kind}: {msg}", flush=True)
        finally:
            hb.cancel()


async def main() -> None:
    if not SESSION:
        raise SystemExit("WORKER_SESSION belum diset")
    print(f"[worker] connecting {WS_URL} device={DEVICE} agents={AGENTS}", flush=True)
    # Auto-reconnect: tahan restart proxy/bot (koneksi WS lewat nginx bisa putus).
    while True:
        try:
            await _session_once()
        except Exception as exc:
            print(f"[worker] disconnected: {exc} — reconnect 3s", flush=True)
        else:
            print("[worker] connection closed — reconnect 3s", flush=True)
        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
