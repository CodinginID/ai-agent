"""Prompt-based fallback adapters untuk workflow agentik (issue #6).

Kalau tidak ada agent CLI (codex/claude/glm) yang di-wire, role dijalankan
lewat AIProvider (Ollama/Qwen) dengan prompt terstruktur. Setiap adapter
parse JSON dari LLM menjadi artefak domain; kalau parsing gagal, fallback ke
artefak minimal yang tetap valid (Plan/Patch/Verdict tidak boleh invalid).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.domain.workflow import Patch, Plan, Verdict
from app.ports.ai_provider import AIProvider

_ARCHITECT_PROMPT = """\
You are the Architect. Produce an implementation plan for the goal below.
Respond with JSON only — no markdown:
{{
  "goal": "restated goal",
  "steps": ["step 1", "step 2"],
  "target_files": ["relative/path/to/file"]
}}

Goal: {goal}
Context: {context}"""

_ENGINEER_PROMPT = """\
You are the Engineer. Implement the plan below. Only touch files listed in
target_files (or files that already exist). Respond with JSON only:
{{
  "summary": "what you changed",
  "changed_files": ["relative/path"],
  "diff": "unified diff or description"
}}

Goal: {goal}
Steps: {steps}
Allowed files: {target_files}"""

_REVIEWER_PROMPT = """\
You are the Reviewer. Decide whether the patch satisfies the plan. If you
reject, you MUST explain why. Respond with JSON only:
{{
  "approved": true,
  "comments": "reasoning"
}}

Goal: {goal}
Patch summary: {summary}
Changed files: {changed_files}
Diff: {diff}"""


def _extract_json(response: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", response, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(v) for v in value if str(v).strip())


@dataclass
class PromptArchitect:
    ai: AIProvider
    model: str = "qwen"

    def make_plan(self, goal: str, trace_id: str, context: str = "") -> Plan:
        response = self.ai.chat(
            _ARCHITECT_PROMPT.format(goal=goal, context=context or "(kosong)")
        )
        data = _extract_json(response) or {}
        steps = _str_tuple(data.get("steps")) or ("Implement: " + goal,)
        return Plan(
            plan_id=str(uuid4()),
            trace_id=trace_id,
            goal=str(data.get("goal") or goal),
            steps=steps,
            target_files=_str_tuple(data.get("target_files")),
            author_model=self.model,
        )


@dataclass
class PromptEngineer:
    ai: AIProvider
    model: str = "qwen"

    def implement(self, plan: Plan) -> Patch:
        response = self.ai.chat(
            _ENGINEER_PROMPT.format(
                goal=plan.goal,
                steps="; ".join(plan.steps),
                target_files=", ".join(plan.target_files) or "(none declared)",
            )
        )
        data = _extract_json(response) or {}
        changed = _str_tuple(data.get("changed_files")) or plan.target_files
        return Patch(
            patch_id=str(uuid4()),
            plan_id=plan.plan_id,
            trace_id=plan.trace_id,
            summary=str(data.get("summary") or "(no summary)"),
            changed_files=changed,
            diff=str(data.get("diff") or ""),
            author_model=self.model,
        )


@dataclass
class PromptReviewer:
    ai: AIProvider
    model: str = "qwen"

    def review(self, patch: Patch, plan: Plan) -> Verdict:
        response = self.ai.chat(
            _REVIEWER_PROMPT.format(
                goal=plan.goal,
                summary=patch.summary,
                changed_files=", ".join(patch.changed_files),
                diff=patch.diff[:2000],
            )
        )
        data = _extract_json(response) or {}
        approved = bool(data.get("approved", False))
        comments = str(data.get("comments") or "")
        if not approved and not comments.strip():
            comments = "(reviewer menolak tanpa komentar eksplisit)"
        return Verdict(
            verdict_id=str(uuid4()),
            patch_id=patch.patch_id,
            trace_id=patch.trace_id,
            approved=approved,
            comments=comments,
            reviewer_model=self.model,
        )
