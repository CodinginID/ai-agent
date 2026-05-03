from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

# Semua intent yang dikenali parser
KNOWN_INTENTS: frozenset[str] = frozenset({
    "server_status", "memory", "disk", "processes",
    "docker_ps", "docker_images", "docker_stats",
    "docker_restart", "docker_logs",
    "git_status", "git_pull",
    "deploy_restart", "run_command",
    "list_files", "whoami",
    "chat", "unknown",
})

# Intent yang punya handler di ACTIONS dan bisa langsung dieksekusi
EXECUTABLE_ACTIONS: frozenset[str] = frozenset({
    "server_status", "memory", "disk", "processes",
    "docker_ps", "docker_images", "docker_stats",
    "git_status", "list_files", "whoami",
})

LOW_RISK: frozenset[str] = frozenset({
    "server_status", "memory", "disk", "processes",
    "docker_ps", "docker_images", "docker_stats",
    "docker_logs", "git_status", "list_files", "whoami",
})

MEDIUM_RISK: frozenset[str] = frozenset({
    "docker_restart", "git_pull", "deploy_restart",
})

HIGH_RISK: frozenset[str] = frozenset({
    "run_command",
})


def risk_level(intent_name: str) -> str:
    if intent_name in LOW_RISK:
        return "low"
    if intent_name in MEDIUM_RISK:
        return "medium"
    if intent_name in HIGH_RISK:
        return "high"
    return "unknown"


@dataclass(frozen=True)
class Intent:
    intent: str
    project_id: str
    confidence: float
    requires_approval: bool
    parameters: dict[str, Any]
    reason: str

    def is_action(self) -> bool:
        return self.intent not in {"chat", "unknown"}

    def risk(self) -> str:
        return risk_level(self.intent)


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    action: str
    parameters: dict[str, Any]
    risk: str

    @classmethod
    def from_intent(cls, intent: Intent, step_number: int = 1) -> PlanStep:
        return cls(
            step_id=str(step_number),
            action=intent.intent,
            parameters=dict(intent.parameters),
            risk=intent.risk(),
        )


@dataclass
class ExecutionPlan:
    plan_id: str
    summary: str
    steps: list[PlanStep]
    requires_approval: bool
    project_id: str
    intent: str

    @classmethod
    def from_intent(cls, intent: Intent, summary: str) -> ExecutionPlan:
        return cls(
            plan_id=str(uuid4()),
            summary=summary,
            steps=[PlanStep.from_intent(intent)],
            requires_approval=intent.requires_approval,
            project_id=intent.project_id,
            intent=intent.intent,
        )

    def short_description(self) -> str:
        step_lines = [
            f"  Step {s.step_id}: {s.action} (risk: {s.risk})"
            for s in self.steps
        ]
        approval = "YA — butuh /approve" if self.requires_approval else "Tidak"
        return (
            f"Plan: {self.summary}\n"
            f"ID: {self.plan_id}\n"
            f"Butuh approval: {approval}\n"
            + "\n".join(step_lines)
        )
