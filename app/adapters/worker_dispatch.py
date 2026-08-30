"""Adapter: WorkerDispatchPort → coroutine ``dispatch_agent_job``.

ExecutionLoop is a synchronous generator run inside ``asyncio.to_thread`` by the
chat handler, so the executing thread has no running event loop. That makes it
safe to spin up a private loop via ``asyncio.run`` to drive the async dispatch
to completion and aggregate its streamed events into a single ``DispatchResult``.

Routing (role → agent + model) is delegated to ``orchestrator/router.pick``,
which is pure and capability-aware. This adapter owns the I/O: reading config
maps and querying the worker capability registry (Redis ``k_caps``).
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.orchestrator.router import pick
from app.ports.worker_dispatch import DispatchResult

logger = logging.getLogger(__name__)


def _role_agent_map() -> dict[str, str]:
    return {
        "engineer": settings.delegate_role_engineer,
        "reviewer": settings.delegate_role_reviewer,
        "research": settings.delegate_role_research,
        "infra": settings.delegate_role_infra,
    }


# Provider (pilihan user) → agent CLI worker. Satu-LLM: semua role pakai ini.
# claude-cli/glm-cli: provider "lokal" eksplisit (tanpa key cloud sama sekali) —
# brain + semua peran dijalankan di worker CLI milik user.
_PROVIDER_AGENT = {
    "claude": "claude",
    "anthropic": "claude",
    "claude-cli": "claude",
    "glm": "glm",
    "zhipu": "glm",
    "glm-cli": "glm",
    "codex": "codex",
}


def _single_agent_override(user_id: str) -> str | None:
    """Agent tunggal untuk SEMUA role bila user mengaktifkan satu LLM.

    Baca preferensi provider per-user; ``mock``/kosong → tak ada override
    (pakai peta role default). Best-effort — kegagalan baca = tak override.
    """
    if not user_id:
        return None
    try:
        from app.adapters.user_provider_config import UserProviderConfigRepository
        from app.composition import _session_factory

        pref = UserProviderConfigRepository(_session_factory()).get(user_id)
    except Exception:
        return None
    if not pref:
        return None
    return _PROVIDER_AGENT.get(pref[0].strip().lower())


def _agent_model_map() -> dict[str, str]:
    """Per-agent model override sourced from existing *_model settings.

    Empty string means "let the agent CLI use its own default model".
    """
    return {
        "claude": settings.claude_model,
        "codex": settings.codex_model,
        "glm": settings.glm_model,
    }


class WorkerDispatchAdapter:
    """Concrete WorkerDispatchPort backed by ``worker_ws.dispatch_agent_job``."""

    def dispatch(self, user_id: str, role: str, prompt: str) -> DispatchResult:
        try:
            return asyncio.run(self.dispatch_async(user_id, role, prompt))
        except RuntimeError as exc:
            # e.g. "asyncio.run() cannot be called from a running event loop"
            logger.warning("worker dispatch could not run: %s", exc)
            return DispatchResult(output="", ok=False, error=f"dispatch runtime error: {exc}")

    async def dispatch_async(
        self, user_id: str, role: str, prompt: str,
    ) -> DispatchResult:
        from app.interfaces.worker_ws import (
            NoWorkerAvailableError,
            dispatch_agent_job,
        )

        available = await self._available_caps(user_id)
        # Satu-LLM: kalau user mengaktifkan provider tunggal, semua role → agent itu.
        single = await asyncio.to_thread(_single_agent_override, user_id)
        role_map = dict.fromkeys(_role_agent_map(), single) if single else _role_agent_map()
        decision = pick(
            role,
            role_agent_map=role_map,
            agent_model_map=_agent_model_map(),
            available_caps=available,
        )
        logger.info(
            "route role=%s → agent=%s model=%s (%s)",
            role, decision.agent, decision.model or "(default)", decision.reason,
        )

        chunks: list[str] = []
        summary = ""
        try:
            async for ev in dispatch_agent_job(
                user_id, decision.agent, prompt,
                extra={"role": decision.role},
                model=decision.model,
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

    async def _available_caps(self, user_id: str) -> frozenset[str] | None:
        """Agents that at least one online worker advertises (via k_caps).

        Returns ``None`` on Redis failure to signal "capabilities unknown" so the
        router skips filtering rather than wrongly excluding every agent.
        """
        from app.adapters.redis_client import get_client, k_caps

        client = get_client()
        found: set[str] = set()
        for agent_id in ("codex", "claude", "glm"):
            try:
                count = await client.scard(k_caps(user_id, agent_id))  # type: ignore[misc]
            except Exception as exc:  # Redis hiccup — degrade to "unknown caps"
                logger.warning("caps lookup failed for %s: %s", agent_id, exc)
                return None
            if int(count) > 0:
                found.add(agent_id)
        # echo is always available locally (no-op safe default).
        found.add("echo")
        return frozenset(found)
