"""TaskRunner — PM plan → GitHub Issue → worker dispatch → close (PR-4).

Turns a free-text request into a durable, auditable task:

    1. PLAN    : PMAgent decomposes the request into ordered steps (TaskPlan).
    2. RECORD  : create a GitHub Issue (PRD body + steps checklist) as the
                 single source of truth for the task.
    3. EXECUTE : dispatch each step to a worker, routed by role (engineer/
                 reviewer/research/infra → different LLMs via the router).
    4. LOG     : comment each step's outcome on the issue (attempt trail).
    5. CLOSE   : close the issue with a summary when all steps succeed; leave
                 it open with a failure comment otherwise (resume later).

Why an issue: unlike an ephemeral in-process loop, the task survives restart,
is auditable, and is collaboratively visible — the trait that makes Octopus
feel like an engineering OS rather than a chatbot.

Hexagonal: depends on ``PMAgentPort``, ``GitHubIssuesPort`` and
``AsyncWorkerDispatchPort`` — never on concrete adapters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.agents.pm import TaskPlan
from app.ports.github_issues import GitHubIssuesPort
from app.ports.pm_agent import PMAgentPort
from app.ports.worker_dispatch import AsyncWorkerDispatchPort

logger = logging.getLogger(__name__)

# Step action prefix → worker role. Server/repo ops stay local (infra);
# file authoring is engineering; everything else explores/reads (research).
_ACTION_ROLE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("file_write", "engineer"),
    ("file_edit", "engineer"),
    ("docker_", "infra"),
    ("git_", "infra"),
    ("server_", "infra"),
    ("memory_", "infra"),
    ("disk_", "infra"),
    ("terminal", "infra"),
)
_DEFAULT_STEP_ROLE = "research"


def role_for_action(action: str) -> str:
    """Map a TaskStep action to a worker role (pure, deterministic)."""
    a = (action or "").strip().lower()
    for prefix, role in _ACTION_ROLE_PREFIXES:
        if a == prefix or a.startswith(prefix):
            return role
    return _DEFAULT_STEP_ROLE


def _issue_body(request: str, plan: TaskPlan) -> str:
    lines = [
        f"**Request:** {request}",
        "",
        f"**Summary:** {plan.summary}",
        f"**Complexity:** {plan.estimated_complexity}",
        "",
        "### Steps",
    ]
    if plan.steps:
        for s in plan.steps:
            lines.append(f"- [ ] {s.order}. {s.description} (`{s.action}`)")
    else:
        lines.append("_(no steps — direct response)_")
    lines += ["", "_Tracked automatically by Octopus TaskRunner._"]
    return "\n".join(lines)


@dataclass(frozen=True)
class StepOutcome:
    order: int
    description: str
    role: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class TaskResult:
    plan: TaskPlan
    issue_number: int | None
    issue_url: str
    outcomes: list[StepOutcome] = field(default_factory=list)
    closed: bool = False
    note: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.outcomes) and all(o.ok for o in self.outcomes)


@dataclass
class TaskRunner:
    pm: PMAgentPort
    github: GitHubIssuesPort
    dispatch: AsyncWorkerDispatchPort
    labels: list[str] = field(default_factory=lambda: ["octopus-task"])

    async def run(self, user_id: str, request: str, context: str = "") -> TaskResult:
        plan = self.pm.plan(request, context)

        # No actionable steps → don't open an issue; nothing to track.
        if not plan.steps:
            return TaskResult(
                plan=plan, issue_number=None, issue_url="",
                note="no steps to execute",
            )

        issue = await self.github.create_issue(
            title=plan.title or f"Task: {request[:60]}",
            body=_issue_body(request, plan),
            labels=self.labels,
        )

        outcomes: list[StepOutcome] = []
        for step in sorted(plan.steps, key=lambda s: s.order):
            role = role_for_action(step.action)
            result = await self.dispatch.dispatch_async(user_id, role, step.description)
            detail = (result.summary or result.output or result.error)[:500]
            outcome = StepOutcome(
                order=step.order,
                description=step.description,
                role=role,
                ok=result.ok,
                detail=detail,
            )
            outcomes.append(outcome)

            status = "✅" if result.ok else "❌"
            await self.github.comment_issue(
                issue.number,
                f"{status} **Step {step.order}** ({role}): {step.description}\n\n```\n{detail}\n```",
            )
            if not result.ok:
                # Stop on first failure — leave issue open for resume/retry.
                return TaskResult(
                    plan=plan,
                    issue_number=issue.number,
                    issue_url=issue.url,
                    outcomes=outcomes,
                    closed=False,
                    note=f"stopped at step {step.order} ({role}): {result.error or 'failed'}",
                )

        await self.github.close_issue(
            issue.number,
            comment=f"All {len(outcomes)} steps completed ✅ — closing.",
        )
        return TaskResult(
            plan=plan,
            issue_number=issue.number,
            issue_url=issue.url,
            outcomes=outcomes,
            closed=True,
            note="completed",
        )
