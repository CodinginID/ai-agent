"""Unit tests untuk ``SkillExecutor`` — pakai fake dispatcher + resolver
sehingga tidak menyentuh DB atau worker WS."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.domain.skills import parse_skill
from app.orchestrator.skill_executor import (
    SkillEvent,
    SkillExecutor,
    build_prompt_for_step,
)

# ── Fake dispatcher ──────────────────────────────────────────────────────────


class FakeDispatcher:
    """Programmable async-iterator dispatcher untuk test executor.

    ``responses`` adalah dict {agent_id: list[list[dict]]}. Tiap nested list
    adalah event-stream untuk satu dispatch call. Call ke-N untuk agent
    tertentu memakai list ke-N.
    """

    def __init__(self, responses: dict[str, list[list[dict[str, Any]]]]) -> None:
        self._responses = responses
        self._call_counts: dict[str, int] = {}
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        user_id: str,
        agent: str,
        prompt: str,
        *,
        timeout_sec: float = 300.0,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        idx = self._call_counts.get(agent, 0)
        self._call_counts[agent] = idx + 1
        self.calls.append({
            "user_id": user_id, "agent": agent, "prompt": prompt, "extra": extra,
        })
        events = self._responses.get(agent, [[]])[idx]
        for ev in events:
            yield ev


def _resolver(mapping: dict[str, str | None]) -> callable:  # type: ignore[valid-type]
    """Fake resolver: role → agent."""
    def f(_user_id: str, role: str) -> str | None:
        return mapping.get(role)
    return f


def _ok_response(text: str, summary: str = "ok") -> list[dict[str, Any]]:
    return [
        {"type": "job_chunk", "text": text},
        {"type": "job_done", "summary": summary},
    ]


def _err_response(message: str) -> list[dict[str, Any]]:
    return [{"type": "job_error", "message": message}]


# ── build_prompt_for_step ────────────────────────────────────────────────────


def test_default_prompt_when_no_deps() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [{"name": "a", "role": "engineer"}],
    })
    out = build_prompt_for_step(skill.steps[0], "do thing", {})
    assert out == "do thing"


def test_default_prompt_prepends_handoff_for_deps() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [
            {"name": "a", "role": "engineer"},
            {"name": "b", "role": "reviewer", "depends_on": ["a"]},
        ],
    })
    step_b = skill.steps[1]
    out = build_prompt_for_step(step_b, "review please", {"a": "engineer output"})
    assert "Hasil dari a:" in out
    assert "engineer output" in out
    assert out.endswith("review please")


def test_default_handoff_skips_missing_outputs() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [
            {"name": "a", "role": "engineer"},
            {"name": "b", "role": "engineer"},
            {"name": "c", "role": "reviewer", "depends_on": ["a", "b"]},
        ],
    })
    out = build_prompt_for_step(skill.steps[2], "review", {"a": "A output"})
    assert "Hasil dari a:" in out
    assert "Hasil dari b:" not in out
    assert "A output" in out


def test_template_substitutes_prompt_and_deps() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [
            {"name": "design", "role": "architect"},
            {
                "name": "build",
                "role": "engineer",
                "depends_on": ["design"],
                "prompt_template": "Brief: {prompt}\nDesign:\n{design}",
            },
        ],
    })
    out = build_prompt_for_step(
        skill.steps[1], "company profile site", {"design": "modern, minimalist"},
    )
    assert out == "Brief: company profile site\nDesign:\nmodern, minimalist"


def test_template_leaves_unknown_placeholders_alone() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [{
            "name": "a", "role": "engineer",
            "prompt_template": "Foo {unknown} {prompt}",
        }],
    })
    out = build_prompt_for_step(skill.steps[0], "p", {})
    assert out == "Foo {unknown} p"


# ── Full executor: happy path ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simple_linear_skill_completes() -> None:
    skill = parse_skill({
        "name": "linear",
        "steps": [
            {"name": "a", "role": "engineer"},
            {"name": "b", "role": "reviewer", "depends_on": ["a"]},
        ],
    })
    dispatcher = FakeDispatcher({
        "codex":  [_ok_response("engineered code")],
        "claude": [_ok_response("review: looks good", summary="LGTM")],
    })
    resolver = _resolver({"engineer": "codex", "reviewer": "claude"})
    executor = SkillExecutor(dispatcher=dispatcher, agent_resolver=resolver)

    events: list[SkillEvent] = []
    async for ev in executor.execute(skill, user_id="u", base_prompt="fix it"):
        events.append(ev)

    types = [e.type for e in events]
    assert types == [
        "skill_started",
        "step_started", "step_chunk", "step_done",
        "step_started", "step_chunk", "step_done",
        "skill_completed",
    ]

    # b's dispatch sees prompt that includes a's output (handoff)
    b_call = dispatcher.calls[1]
    assert "engineered code" in b_call["prompt"]
    assert "fix it" in b_call["prompt"]

    # Final event has both results in order
    final = events[-1]
    results = final.payload["results"]
    assert [r["step_name"] for r in results] == ["a", "b"]
    assert results[0]["agent"] == "codex"
    assert results[1]["summary"] == "LGTM"


@pytest.mark.asyncio
async def test_diamond_dag_executes_in_topological_order() -> None:
    """design → (copy, code-prep) → review (depends on both)."""
    skill = parse_skill({
        "name": "diamond",
        "steps": [
            {"name": "design",  "role": "architect"},
            {"name": "copy",    "role": "engineer", "depends_on": ["design"]},
            {"name": "code",    "role": "engineer", "depends_on": ["design"]},
            {"name": "review",  "role": "reviewer", "depends_on": ["copy", "code"]},
        ],
    })
    dispatcher = FakeDispatcher({
        "glm":    [_ok_response("DESIGN_OUT")],
        "codex":  [_ok_response("COPY_OUT"), _ok_response("CODE_OUT")],
        "claude": [_ok_response("REVIEW_OUT")],
    })
    resolver = _resolver({
        "architect": "glm", "engineer": "codex", "reviewer": "claude",
    })
    executor = SkillExecutor(dispatcher=dispatcher, agent_resolver=resolver)

    events: list[SkillEvent] = []
    async for ev in executor.execute(skill, user_id="u", base_prompt="build site"):
        events.append(ev)

    completed = next(e for e in events if e.type == "skill_completed")
    names = [r["step_name"] for r in completed.payload["results"]]
    assert names == ["design", "copy", "code", "review"]

    # review's prompt should include both COPY_OUT and CODE_OUT
    review_call = dispatcher.calls[-1]
    assert "COPY_OUT" in review_call["prompt"]
    assert "CODE_OUT" in review_call["prompt"]


# ── Failure paths ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skill_fails_when_role_has_no_agent() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [
            {"name": "a", "role": "engineer"},
            {"name": "b", "role": "reviewer", "depends_on": ["a"]},
        ],
    })
    dispatcher = FakeDispatcher({"codex": [_ok_response("A_OUT")]})
    # Reviewer tidak ter-resolve → step b harus fail
    resolver = _resolver({"engineer": "codex", "reviewer": None})
    executor = SkillExecutor(dispatcher=dispatcher, agent_resolver=resolver)

    events: list[SkillEvent] = []
    async for ev in executor.execute(skill, user_id="u", base_prompt="x"):
        events.append(ev)

    types = [e.type for e in events]
    assert types == [
        "skill_started",
        "step_started", "step_chunk", "step_done",
        "step_failed", "skill_failed",
    ]
    failed = events[-1]
    assert failed.payload["failed_step"] == "b"
    assert "reviewer" in failed.payload["reason"]


@pytest.mark.asyncio
async def test_skill_fails_on_dispatcher_job_error() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [{"name": "only", "role": "engineer"}],
    })
    dispatcher = FakeDispatcher({"codex": [_err_response("worker exploded")]})
    resolver = _resolver({"engineer": "codex"})
    executor = SkillExecutor(dispatcher=dispatcher, agent_resolver=resolver)

    events: list[SkillEvent] = []
    async for ev in executor.execute(skill, user_id="u", base_prompt="x"):
        events.append(ev)

    types = [e.type for e in events]
    assert types == ["skill_started", "step_started", "step_failed", "skill_failed"]
    assert "worker exploded" in events[-1].payload["reason"]


@pytest.mark.asyncio
async def test_halts_after_first_failure_no_further_dispatch() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [
            {"name": "a", "role": "engineer"},
            {"name": "b", "role": "reviewer", "depends_on": ["a"]},
        ],
    })
    dispatcher = FakeDispatcher({
        "codex":  [_err_response("step a failed")],
        # Claude responses prepared but should never be called
        "claude": [_ok_response("should not appear")],
    })
    resolver = _resolver({"engineer": "codex", "reviewer": "claude"})
    executor = SkillExecutor(dispatcher=dispatcher, agent_resolver=resolver)

    events: list[SkillEvent] = []
    async for ev in executor.execute(skill, user_id="u", base_prompt="x"):
        events.append(ev)

    # Step b dispatched? Should NOT be — execution halted at a.
    assert all(call["agent"] != "claude" for call in dispatcher.calls)
    assert events[-1].type == "skill_failed"


# ── Event payload sanity ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skill_started_event_includes_step_count() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [
            {"name": "a", "role": "engineer"},
            {"name": "b", "role": "reviewer", "depends_on": ["a"]},
        ],
    })
    dispatcher = FakeDispatcher({
        "codex": [_ok_response("a")],
        "claude": [_ok_response("b")],
    })
    resolver = _resolver({"engineer": "codex", "reviewer": "claude"})
    executor = SkillExecutor(dispatcher=dispatcher, agent_resolver=resolver)

    first: SkillEvent | None = None
    async for ev in executor.execute(skill, user_id="u", base_prompt="p"):
        first = ev
        break
    assert first is not None
    assert first.type == "skill_started"
    assert first.payload == {"skill_name": "x", "step_count": 2}


@pytest.mark.asyncio
async def test_step_extra_passed_to_dispatcher() -> None:
    """``extra`` dict harus include role + skill name + step name."""
    skill = parse_skill({
        "name": "myskill",
        "steps": [{"name": "lonely", "role": "engineer"}],
    })
    dispatcher = FakeDispatcher({"codex": [_ok_response("ok")]})
    resolver = _resolver({"engineer": "codex"})
    executor = SkillExecutor(dispatcher=dispatcher, agent_resolver=resolver)

    async for _ in executor.execute(skill, user_id="u", base_prompt="p"):
        pass

    extra = dispatcher.calls[0]["extra"]
    assert extra == {"role": "engineer", "skill": "myskill", "step": "lonely"}
