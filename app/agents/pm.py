"""Project Manager Agent — breaks down complex tasks into steps.

Uses the configured AI provider (Qwen/Ollama) to parse a request into an
ordered list of action steps that the ActionRegistry can execute.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ports.ai_provider import AIProvider

_AVAILABLE_ACTIONS: tuple[str, ...] = (
    "server_status", "memory_usage", "disk_usage",
    "docker_ps", "docker_logs", "docker_restart", "docker_stats", "docker_build", "docker_exec",
    "git_status", "git_diff", "git_log", "git_add", "git_commit", "git_push", "git_branch",
    "file_read", "file_write", "file_list", "file_edit",
    "github_create_issue", "github_comment", "github_list_issues", "github_close_issue",
    "terminal",
)

_PLANNING_PROMPT_TEMPLATE = """\
You are a Project Manager AI. Break down this request into actionable steps.

Available actions: {actions}

Request: {request}
Context: {context}

Respond with JSON only — no markdown, no explanation outside the JSON block:
{{
  "title": "Brief task title (max 80 chars)",
  "summary": "What we are doing and why",
  "estimated_complexity": "simple|medium|complex",
  "steps": [
    {{"order": 1, "description": "...", "action": "...", "params": {{}}}},
    {{"order": 2, "description": "...", "action": "...", "params": {{...}}}}
  ]
}}"""


@dataclass(frozen=True)
class TaskStep:
    order: int
    description: str
    action: str
    params: dict


@dataclass(frozen=True)
class TaskPlan:
    title: str
    summary: str
    steps: list[TaskStep]
    estimated_complexity: str  # "simple" | "medium" | "complex"


@dataclass
class PMAgent:
    """Planning agent that converts free-text requests into TaskPlan objects."""

    ai_provider: AIProvider
    available_actions: tuple[str, ...] = field(default_factory=lambda: _AVAILABLE_ACTIONS)

    def plan(self, request: str, context: str = "") -> TaskPlan:
        """Given a request, return a TaskPlan with ordered steps.

        Uses the AI provider to break down complex requests. Falls back to a
        single-step no-op plan when the AI response is malformed.
        """
        prompt = self._build_planning_prompt(request, context)
        try:
            response = self.ai_provider.chat(prompt)
        except Exception as exc:
            return TaskPlan(
                title="Error",
                summary=f"AI provider gagal: {exc}",
                steps=[],
                estimated_complexity="simple",
            )
        return self._parse_plan(response)

    # ── private ───────────────────────────────────────────────────────────────

    def _build_planning_prompt(self, request: str, context: str) -> str:
        return _PLANNING_PROMPT_TEMPLATE.format(
            actions=", ".join(self.available_actions),
            request=request,
            context=context or "(kosong)",
        )

    def _parse_plan(self, response: str) -> TaskPlan:
        """Parse AI JSON response into a TaskPlan.

        Extracts the first JSON object found in the response (the model
        sometimes wraps output in backticks or adds preamble text).
        Falls back to a summary-only plan when JSON is absent or invalid.
        """
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if not json_match:
            return TaskPlan(
                title="Direct response",
                summary=response[:200],
                steps=[],
                estimated_complexity="simple",
            )

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return TaskPlan(
                title="Task",
                summary=response[:200],
                steps=[],
                estimated_complexity="simple",
            )

        raw_steps = data.get("steps", [])
        steps = []
        for i, s in enumerate(raw_steps):
            if not isinstance(s, dict):
                continue
            steps.append(TaskStep(
                order=int(s.get("order", i + 1)),
                description=str(s.get("description", "")),
                action=str(s.get("action", "")),
                params=s.get("params", {}) if isinstance(s.get("params"), dict) else {},
            ))

        return TaskPlan(
            title=str(data.get("title", "Task"))[:80],
            summary=str(data.get("summary", "")),
            steps=steps,
            estimated_complexity=str(data.get("estimated_complexity", "medium")),
        )
