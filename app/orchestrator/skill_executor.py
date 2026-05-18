"""Skill executor — Phase 1 sequential DAG.

Walk steps dalam topological order, dispatch tiap step ke agent yang assigned
ke role-nya, kumpulin output, lewatkan ke step berikutnya via prompt template
atau default hand-off block.

Halt-on-first-failure: kalau satu step gagal (agent unavailable, dispatcher
emit ``job_error``, worker timeout), emit ``skill_failed`` dan stop.

Dependencies di-inject (DI) lewat ``dispatcher`` dan ``agent_resolver``:

- ``dispatcher`` adalah async-iterator-yielding callable (signature sama dengan
  ``app.interfaces.worker_ws.dispatch_agent_job``).
- ``agent_resolver`` adalah sync callable yang map ``(user_id, role)`` ke
  ``agent_id`` (mis. ``UserAgentConfigRepository.agent_for_role``).

Inversion-of-control ini bikin executor testable tanpa real WS/DB plumbing.

Phase 2 (manager pattern with revisions) dan Phase 3 (debate loop) akan
extend executor ini di branch terpisah.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from app.domain.skills import Skill, Step, topological_order

# ── Public types ──────────────────────────────────────────────────────────────

DispatcherFn = Callable[..., AsyncIterator[dict[str, Any]]]
AgentResolverFn = Callable[[str, str], str | None]


@dataclass(frozen=True)
class StepResult:
    step_name: str
    role: str
    agent: str
    output: str
    summary: str = ""


@dataclass(frozen=True)
class SkillEvent:
    """Event yang di-yield executor selama eksekusi.

    Type list:
    - ``skill_started`` — payload: ``{skill_name, step_count}``
    - ``step_started`` — payload: ``{step_name, role, agent, prompt}``
    - ``step_chunk`` — payload: ``{step_name, text}`` (forward dari dispatcher)
    - ``step_done`` — payload: ``{step_name, output, summary}``
    - ``step_failed`` — payload: ``{step_name, reason}``
    - ``skill_completed`` — payload: ``{results: list[StepResult-as-dict]}``
    - ``skill_failed`` — payload: ``{reason, failed_step: str | None}``
    """

    type: str
    payload: dict[str, Any] = field(default_factory=dict)


# ── Prompt building (handoff) ─────────────────────────────────────────────────


def build_prompt_for_step(
    step: Step,
    base_prompt: str,
    prev_outputs: dict[str, str],
) -> str:
    """Hasilkan prompt akhir untuk step.

    Kalau ``step.prompt_template`` di-set:
        - ``{prompt}`` → base_prompt user
        - ``{<dep_name>}`` → output step bernama ``<dep_name>`` (dari depends_on)
        - Placeholder yang tidak ada di outputs di-leave as-is (caller bisa
          interpret kalau perlu).

    Kalau tidak ada template:
        - Default hand-off — prepend "Hasil dari <dep>" block untuk tiap
          depends_on yang punya output.
    """
    if step.prompt_template is not None:
        rendered = step.prompt_template.replace("{prompt}", base_prompt)
        for dep_name, dep_output in prev_outputs.items():
            rendered = rendered.replace(f"{{{dep_name}}}", dep_output)
        return rendered

    if not step.depends_on:
        return base_prompt

    parts: list[str] = []
    for dep in step.depends_on:
        out = prev_outputs.get(dep)
        if out is None:
            continue
        parts.append(f"Hasil dari {dep}:\n{out}")
    if not parts:
        return base_prompt
    return "\n\n".join(parts) + "\n\n---\n\n" + base_prompt


# ── Executor ──────────────────────────────────────────────────────────────────


@dataclass
class SkillExecutor:
    dispatcher: DispatcherFn
    agent_resolver: AgentResolverFn

    async def execute(
        self,
        skill: Skill,
        *,
        user_id: str,
        base_prompt: str,
    ) -> AsyncIterator[SkillEvent]:
        """Run skill end-to-end. Yield events untuk observability + UI streaming."""
        order = topological_order(skill)
        yield SkillEvent(
            "skill_started",
            {"skill_name": skill.name, "step_count": len(order)},
        )

        results: dict[str, StepResult] = {}
        outputs: dict[str, str] = {}

        for step in order:
            agent = self.agent_resolver(user_id, step.role)
            if agent is None:
                reason = (
                    f"Tidak ada agent assigned ke role '{step.role}' untuk user. "
                    "Set via /agents."
                )
                yield SkillEvent("step_failed", {"step_name": step.name, "reason": reason})
                yield SkillEvent(
                    "skill_failed",
                    {"reason": reason, "failed_step": step.name},
                )
                return

            prompt = build_prompt_for_step(step, base_prompt, outputs)
            yield SkillEvent(
                "step_started",
                {
                    "step_name": step.name,
                    "role": step.role,
                    "agent": agent,
                    "prompt": prompt,
                },
            )

            step_output_buf: list[str] = []
            step_summary = ""
            failed_reason: str | None = None

            async for ev in self.dispatcher(
                user_id, agent, prompt,
                extra={"role": step.role, "skill": skill.name, "step": step.name},
            ):
                kind = ev.get("type", "")
                if kind == "job_chunk":
                    text = str(ev.get("text", ""))
                    step_output_buf.append(text)
                    yield SkillEvent(
                        "step_chunk",
                        {"step_name": step.name, "text": text},
                    )
                elif kind == "job_done":
                    step_summary = str(ev.get("summary", ""))
                    break
                elif kind == "job_error":
                    failed_reason = str(ev.get("message", "dispatcher reported error"))
                    break
                # Event lain (job_queued, job_started) di-skip — tidak relevan
                # untuk skill-level state machine.

            if failed_reason is not None:
                yield SkillEvent(
                    "step_failed",
                    {"step_name": step.name, "reason": failed_reason},
                )
                yield SkillEvent(
                    "skill_failed",
                    {"reason": failed_reason, "failed_step": step.name},
                )
                return

            output = "".join(step_output_buf).strip()
            outputs[step.name] = output
            results[step.name] = StepResult(
                step_name=step.name,
                role=step.role,
                agent=agent,
                output=output,
                summary=step_summary,
            )
            yield SkillEvent(
                "step_done",
                {
                    "step_name": step.name,
                    "output": output,
                    "summary": step_summary,
                },
            )

        yield SkillEvent(
            "skill_completed",
            {
                "results": [
                    {
                        "step_name": r.step_name,
                        "role": r.role,
                        "agent": r.agent,
                        "output": r.output,
                        "summary": r.summary,
                    }
                    for r in _ordered_results(results, order)
                ],
            },
        )


def _ordered_results(
    results: dict[str, StepResult],
    order: Iterable[Step],
) -> list[StepResult]:
    """Return results dalam urutan eksekusi (stable untuk UI rendering)."""
    return [results[s.name] for s in order if s.name in results]
