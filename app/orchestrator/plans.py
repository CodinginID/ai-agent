from __future__ import annotations

from uuid import uuid4

from app.intents.schemas import ExecutionPlan, Intent, PlanStep

_SUMMARIES: dict[str, str] = {
    "server_status":          "Check server health and resource usage",
    "memory":                 "Check RAM and swap usage",
    "disk":                   "Check disk usage across partitions",
    "processes":              "List active processes by CPU/memory",
    "docker_ps":              "List running Docker containers",
    "docker_images":          "List Docker images",
    "docker_stats":           "Show Docker container resource stats",
    "docker_restart":         "Restart a Docker container",
    "docker_logs":            "Show Docker container logs",
    "docker_compose_ps":      "Show docker compose services status",
    "docker_compose_pull":    "Pull latest images for compose services",
    "docker_compose_build":   "Build docker compose services",
    "docker_compose_up":      "Start docker compose services",
    "docker_compose_restart": "Restart docker compose services",
    "git_status":             "Show Git repository status",
    "git_pull":               "Pull latest code from remote",
    "list_files":             "List files in project directory",
    "whoami":                 "Show bot identity and working directory",
    "deploy":                 "Full deploy: git pull → build → up → health check",
    "deploy_restart":         "Restart the application service",
    "rollback":               "Rollback to previous deployment",
    "service_health_check":   "Check if a service endpoint is responding",
    "run_command":            "Run a custom shell command",
}


class PlanGenerator:
    def generate(self, intent: Intent) -> ExecutionPlan:
        summary = _SUMMARIES.get(intent.intent, f"Execute: {intent.intent}")
        return ExecutionPlan.from_intent(intent, summary)

    def generate_rollback(self, project_id: str, pre_deploy_commit: str) -> ExecutionPlan:
        """Create a rollback plan: reset to pre-deploy commit + compose up."""
        steps = [
            PlanStep(
                step_id="1",
                action="run_command",
                parameters={"command": f"git reset --hard {pre_deploy_commit}"},
                risk="high",
            ),
            PlanStep(
                step_id="2",
                action="docker_compose_up",
                parameters={},
                risk="high",
            ),
        ]
        return ExecutionPlan(
            plan_id=str(uuid4()),
            summary=f"Rollback ke commit {pre_deploy_commit[:8]}",
            steps=steps,
            requires_approval=True,
            project_id=project_id,
            intent="rollback",
        )
