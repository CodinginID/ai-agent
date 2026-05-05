from __future__ import annotations

from app.intents.schemas import ExecutionPlan, Intent

_SUMMARIES: dict[str, str] = {
    "server_status": "Check server health and resource usage",
    "memory": "Check RAM and swap usage",
    "disk": "Check disk usage across partitions",
    "processes": "List active processes by CPU/memory",
    "docker_ps": "List running Docker containers",
    "docker_images": "List Docker images",
    "docker_stats": "Show Docker container resource stats",
    "docker_restart": "Restart a Docker container",
    "docker_logs": "Show Docker container logs",
    "git_status": "Show Git repository status",
    "git_pull": "Pull latest code from remote",
    "list_files": "List files in project directory",
    "whoami": "Show bot identity and working directory",
    "deploy_restart": "Restart the application service",
    "run_command": "Run a custom shell command",
}


class PlanGenerator:
    def generate(self, intent: Intent) -> ExecutionPlan:
        summary = _SUMMARIES.get(intent.intent, f"Execute: {intent.intent}")
        return ExecutionPlan.from_intent(intent, summary)
