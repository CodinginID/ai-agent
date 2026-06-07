"""Adapter: WorkerDispatchPort → coroutine ``dispatch_agent_job``.

ExecutionLoop is a synchronous generator run inside ``asyncio.to_thread`` by the
chat handler, so the executing thread has no running event loop. That makes it
safe to spin up a private loop via ``asyncio.run`` to drive the async dispatch
to completion and aggregate its streamed events into a single ``DispatchResult``.

Role → agent mapping is intentionally minimal here (PR-1 scope). The richer
role→model router lands in a later PR (see docs/ORCHESTRATOR.md); this adapter
only needs to turn a role into a concrete agent name the worker understands.
"""

from __future__ import annotations

import asyncio
import logging

from app.ports.worker_dispatch import DispatchResult

logger = logging.getLogger(__name__)

# Minimal role → agent mapping. Replaced by orchestrator/router.py in PR-2.
# infra stays on a local agent by policy (server ops must not leave the box);
# until a local coding agent exists, it falls back to echo (no-op safe default).
_ROLE_TO_AGENT: dict[str, str] = {
    "engineer": "claude",
    "reviewer": "glm",
    "research": "codex",
    "infra": "echo",
}
_DEFAULT_AGENT = "claude"


class WorkerDispatchAdapter:
    """Concrete WorkerDispatchPort backed by ``worker_ws.dispatch_agent_job``."""

    def dispatch(self, user_id: str, role: str, prompt: str) -> DispatchResult:
        agent = _ROLE_TO_AGENT.get(role, _DEFAULT_AGENT)
        try:
            return asyncio.run(self._dispatch_async(user_id, agent, role, prompt))
        except RuntimeError as exc:
            # e.g. "asyncio.run() cannot be called from a running event loop"
            logger.warning("worker dispatch could not run: %s", exc)
            return DispatchResult(output="", ok=False, error=f"dispatch runtime error: {exc}")

    async def _dispatch_async(
        self, user_id: str, agent: str, role: str, prompt: str,
    ) -> DispatchResult:
        from app.interfaces.worker_ws import (
            NoWorkerAvailableError,
            dispatch_agent_job,
        )

        chunks: list[str] = []
        summary = ""
        try:
            async for ev in dispatch_agent_job(
                user_id, agent, prompt, extra={"role": role},
            ):
                kind = ev.get("type", "")
                if kind == "job_chunk":
                    chunks.append(str(ev.get("text", "")))
                elif kind == "job_done":
                    summary = str(ev.get("summary", ""))
                    return DispatchResult(
                        output="".join(chunks).strip(),
                        summary=summary,
                        ok=True,
                    )
                elif kind == "job_error":
                    return DispatchResult(
                        output="".join(chunks).strip(),
                        summary=summary,
                        ok=False,
                        error=str(ev.get("message", "worker error")),
                    )
        except NoWorkerAvailableError as exc:
            return DispatchResult(output="", ok=False, error=str(exc))

        # Stream ended without job_done/job_error.
        return DispatchResult(
            output="".join(chunks).strip(),
            summary=summary,
            ok=False,
            error="worker stream ended without completion",
        )
