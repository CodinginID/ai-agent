"""TUI worker: maintain WS connection ke backend, eksekusi job sebagai agent.

Tugas:
1. Connect ke ``ws://backend/ws/worker?session=<token>`` saat session aktif
2. Listen ``{"type":"job","job_id":...,"agent":...,"prompt":...}``
3. Spawn subprocess agent (codex/claude/glm/echo)
4. Stream stdout → kirim ``job_chunk`` per baris
5. Saat selesai → kirim ``job_done`` dengan exit_code + summary
6. Handle reconnect dengan backoff exponential

Agent yang didukung:
- ``echo``  : mock — balas prompt apa adanya (untuk test handshake)
- ``codex`` : subprocess ``codex exec`` dengan sandbox
- ``claude``: subprocess ``claude --print``
- ``glm``   : subprocess ``glm`` (kalau enabled)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import socket
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse, urlunparse

import websockets
from websockets.exceptions import ConnectionClosed

from app.config import settings
from app.tui import _state
from app.tui._output import println

logger = logging.getLogger(__name__)

_RECONNECT_INITIAL_DELAY = 2.0
_RECONNECT_MAX_DELAY = 60.0
_HEARTBEAT_INTERVAL_SEC = 30.0

_background_tasks: set[asyncio.Task[None]] = set()


def _ws_url(token: str) -> str:
    """Convert HTTP APP_URL ke WS URL."""
    parsed = urlparse(settings.app_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "/ws/worker", "", f"session={token}", ""))


# ── agent runners ────────────────────────────────────────────────────────────
#
# Setiap agent runner adalah ``async def(prompt) -> AsyncIterator[dict]``:
#   yield {"type": "chunk", "text": "..."}
#   yield {"type": "done",  "exit_code": int, "summary": str}
#   atau yield {"type": "error", "message": str}
# Caller (`_execute_agent`) yang convert ke pesan WS.

class AgentNotInstalledError(Exception):
    """CLI binary tidak ditemukan di PATH user."""


async def _spawn_streaming(
    args: list[str],
    *,
    timeout_sec: float,
) -> AsyncIterator[dict[str, Any]]:
    """Jalankan ``args`` sebagai subprocess, stream stdout per chunk.

    Cancel-aware: kalau task di-cancel, subprocess di-terminate.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        async with asyncio.timeout(timeout_sec):
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(1024)
                if not chunk:
                    break
                yield {"type": "chunk", "text": chunk.decode("utf-8", errors="replace")}
            await proc.wait()
        yield {
            "type": "done",
            "exit_code": proc.returncode if proc.returncode is not None else -1,
            "summary": (
                f"exit {proc.returncode}" if proc.returncode == 0
                else f"failed with exit {proc.returncode}"
            ),
        }
    except TimeoutError:
        proc.kill()
        await proc.wait()
        yield {
            "type": "error",
            "message": f"timeout {timeout_sec:.0f}s — subprocess di-kill",
        }
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    except Exception as exc:
        proc.kill()
        await proc.wait()
        yield {"type": "error", "message": f"{type(exc).__name__}: {exc}"}


async def _agent_echo(prompt: str) -> AsyncIterator[dict[str, Any]]:
    """Mock agent — balas prompt apa adanya, 2 chunks untuk test stream."""
    yield {"type": "chunk", "text": f"[echo] received: {prompt}\n"}
    await asyncio.sleep(0.1)
    yield {"type": "chunk", "text": "[echo] done.\n"}
    yield {"type": "done", "exit_code": 0, "summary": f"echoed {len(prompt)} chars"}


async def _agent_codex(prompt: str) -> AsyncIterator[dict[str, Any]]:
    if not settings.enable_codex:
        yield {"type": "error", "message": "Codex belum aktif. Set ENABLE_CODEX=true di .env."}
        return
    bin_path = shutil.which(settings.codex_bin)
    if not bin_path:
        yield {"type": "error", "message": f"Codex CLI tidak ditemukan: {settings.codex_bin}"}
        return

    args = [
        bin_path, "exec",
        "--cd", str(settings.agent_workdir),
        "--sandbox", settings.codex_sandbox,
        "--ask-for-approval", "never",
        "--skip-git-repo-check",
        "--ephemeral",
        "--color", "never",
    ]
    if settings.codex_model:
        args.extend(["--model", settings.codex_model])
    args.append(prompt)

    async for event in _spawn_streaming(args, timeout_sec=settings.agent_timeout):
        yield event


async def _agent_claude(prompt: str) -> AsyncIterator[dict[str, Any]]:
    if not settings.enable_claude:
        yield {"type": "error", "message": "Claude belum aktif. Set ENABLE_CLAUDE=true di .env."}
        return
    bin_path = shutil.which(settings.claude_bin)
    if not bin_path:
        yield {"type": "error", "message": f"Claude CLI tidak ditemukan: {settings.claude_bin}"}
        return

    args = [
        bin_path,
        "--print",
        "--no-session-persistence",
        "--permission-mode", settings.claude_permission_mode,
        "--output-format", "text",
    ]
    if settings.claude_tools:
        args.extend(["--tools", settings.claude_tools])
    if settings.claude_allowed_tools and settings.claude_allowed_tools.lower() != "default":
        args.extend(["--allowedTools", settings.claude_allowed_tools])
    if settings.claude_model:
        args.extend(["--model", settings.claude_model])
    args.append(prompt)

    async for event in _spawn_streaming(args, timeout_sec=settings.agent_timeout):
        yield event


async def _agent_glm(prompt: str) -> AsyncIterator[dict[str, Any]]:
    if not settings.enable_glm:
        yield {"type": "error", "message": "GLM belum aktif. Set ENABLE_GLM=true di .env."}
        return
    bin_path = shutil.which(settings.glm_bin)
    if not bin_path:
        yield {"type": "error", "message": f"GLM CLI tidak ditemukan: {settings.glm_bin}"}
        return

    args = [bin_path]
    if settings.glm_model:
        args.extend(["--model", settings.glm_model])
    args.append(prompt)

    async for event in _spawn_streaming(args, timeout_sec=settings.agent_timeout):
        yield event


_AGENTS = {
    "echo":   _agent_echo,
    "codex":  _agent_codex,
    "claude": _agent_claude,
    "glm":    _agent_glm,
}


async def _execute_agent(
    ws: websockets.ClientConnection,
    job_id: str,
    agent: str,
    prompt: str,
) -> None:
    """Jalankan agent → stream chunk via WS → akhiri dengan job_done/job_error."""
    runner = _AGENTS.get(agent)
    if runner is None:
        await ws.send(json.dumps({
            "type": "job_error",
            "job_id": job_id,
            "message": f"agent '{agent}' belum didukung. Available: {', '.join(_AGENTS)}",
        }))
        return

    try:
        async for event in runner(prompt):
            kind = event.get("type", "")
            if kind == "chunk":
                await ws.send(json.dumps({
                    "type": "job_chunk",
                    "job_id": job_id,
                    "text": event.get("text", ""),
                }))
            elif kind == "done":
                await ws.send(json.dumps({
                    "type": "job_done",
                    "job_id": job_id,
                    "exit_code": event.get("exit_code", 0),
                    "summary": event.get("summary", ""),
                }))
                return
            elif kind == "error":
                await ws.send(json.dumps({
                    "type": "job_error",
                    "job_id": job_id,
                    "message": event.get("message", "agent error"),
                }))
                return
    except asyncio.CancelledError:
        # WS closed atau task cancelled — subprocess sudah di-kill di _spawn_streaming.
        raise
    except Exception as exc:
        logger.exception("agent %s crashed", agent)
        with contextlib.suppress(ConnectionClosed):
            await ws.send(json.dumps({
                "type": "job_error",
                "job_id": job_id,
                "message": f"{type(exc).__name__}: {exc}",
            }))


# ── main worker loop ─────────────────────────────────────────────────────────

async def _handle_message(ws: websockets.ClientConnection, raw: str) -> None:
    try:
        msg: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return

    kind = msg.get("type", "")
    if kind == "registered":
        worker_id = msg.get("worker_id", "?")
        logger.info("worker registered: id=%s", worker_id)
        # Tampilkan ke user juga (ringan, tidak block UI)
        with contextlib.suppress(Exception):
            println("class:dim", f"  ✓ worker terhubung ke backend (id={worker_id})")
    elif kind == "heartbeat_ack":
        pass
    elif kind == "job":
        job_id = str(msg.get("job_id", ""))
        agent = str(msg.get("agent", ""))
        prompt = str(msg.get("prompt", ""))
        if job_id and agent:
            task = asyncio.create_task(_execute_agent(ws, job_id, agent, prompt))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
    else:
        logger.debug("unknown msg from backend: %s", kind)


async def _heartbeat_loop(ws: websockets.ClientConnection) -> None:
    """Kirim heartbeat tiap N detik supaya TTL Redis presence di-refresh."""
    try:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_SEC)
            await ws.send(json.dumps({"type": "heartbeat"}))
    except (asyncio.CancelledError, ConnectionClosed):
        return


def _detect_capabilities() -> dict[str, dict[str, Any]]:
    """Cek CLI binary mana yang terinstall di mesin user."""
    caps: dict[str, dict[str, Any]] = {}
    for agent_id, bin_name in (
        ("codex", settings.codex_bin),
        ("claude", settings.claude_bin),
        ("glm", settings.glm_bin),
    ):
        path = shutil.which(bin_name)
        caps[agent_id] = {
            "installed": path is not None,
            "path": path or "",
            "bin": bin_name,
        }
    return caps


async def _connection_session(token: str) -> None:
    """Satu attempt connection — keluar saat WS close, caller akan retry."""
    url = _ws_url(token)
    logger.info("worker connecting: %s", url.split("?")[0])
    # proxy=None: skip env-based proxy. HTTPS_PROXY di .env ditujukan untuk
    # bot di VPS, bukan untuk WS lokal TUI ↔ backend.
    async with websockets.connect(
        url,
        ping_interval=20,
        ping_timeout=10,
        proxy=None,
    ) as ws:
        # Setelah connected, advertise capability — biar backend tahu CLI mana
        # yang installed di mesin user. /agents endpoint pakai info ini untuk
        # warn kalau user enable agent tapi binary-nya belum terpasang.
        await ws.send(json.dumps({
            "type": "capabilities",
            "device_name": socket.gethostname(),
            "agents": _detect_capabilities(),
        }))
        hb_task = asyncio.create_task(_heartbeat_loop(ws))
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                await _handle_message(ws, raw)
        finally:
            hb_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await hb_task


async def run_worker_loop() -> None:
    """Loop dengan reconnect backoff. Cancel task ini saat TUI exit / logout."""
    delay = _RECONNECT_INITIAL_DELAY
    while _state.running[0]:
        session = _state.active_session
        if session is None:
            await asyncio.sleep(2.0)
            continue
        token = session.token
        try:
            await _connection_session(token)
            delay = _RECONNECT_INITIAL_DELAY  # connection sehat → reset backoff
        except asyncio.CancelledError:
            raise
        except ConnectionClosed:
            logger.info("worker WS closed, reconnect in %.1fs", delay)
        except Exception as exc:
            logger.warning("worker error: %s — reconnect in %.1fs", exc, delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, _RECONNECT_MAX_DELAY)
