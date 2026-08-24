"""RedisHandoffContextProvider — prepend prior role's last output to a prompt."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from app.adapters.agent_context import build_handoff_prefix, fetch_role

# Roles that inherit context from a prior role. Reviewer and architect typically
# consume the engineer's most recent output as additional context.
_HANDOFF_FROM: dict[str, str] = {
    "reviewer":  "engineer",
    "architect": "engineer",
}


class RedisHandoffContextProvider:
    def prepend_context(self, project_id: str, role: str, prompt: str) -> str:
        prev_role = _HANDOFF_FROM.get(role)
        if not prev_role:
            return prompt

        def _run() -> dict[str, Any] | None:
            # Fresh event loop in a dedicated thread — safe regardless of outer loop state.
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(fetch_role(project_id, prev_role))
            finally:
                loop.close()

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                prev = pool.submit(_run).result(timeout=5)
        except Exception:
            return prompt

        if not prev:
            return prompt
        return build_handoff_prefix(prev, role) + prompt
