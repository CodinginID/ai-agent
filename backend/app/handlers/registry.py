from __future__ import annotations

from app.config import settings
from app.executor.actions import ActionMeta, ActionRegistry
from app.handlers.actions import (
    action_disk,
    action_docker_images,
    action_docker_ps,
    action_docker_stats,
    action_git_status,
    action_list_files,
    action_memory,
    action_processes,
    action_server_status,
    action_whoami,
)

_ACTIONS: dict[str, object] = {
    "server_status": action_server_status,
    "memory": action_memory,
    "disk": action_disk,
    "processes": action_processes,
    "docker_ps": action_docker_ps,
    "docker_images": action_docker_images,
    "docker_stats": action_docker_stats,
    "git_status": action_git_status,
    "list_files": action_list_files,
    "whoami": action_whoami,
}

_ACTION_METADATA: list[tuple[str, str, str]] = [
    ("server_status", "Check server health, uptime, CPU, RAM, load, disk", "low"),
    ("memory",        "Check RAM and swap usage",                          "low"),
    ("disk",          "Check disk usage across partitions",                "low"),
    ("processes",     "List top processes by CPU/memory",                  "low"),
    ("docker_ps",     "List running Docker containers",                    "low"),
    ("docker_images", "List Docker images",                                "low"),
    ("docker_stats",  "Show Docker container resource stats",              "low"),
    ("git_status",    "Show Git repository status",                        "low"),
    ("list_files",    "List files in project directory",                   "low"),
    ("whoami",        "Show bot identity and working directory",           "low"),
]


def _build_registry() -> ActionRegistry:
    from app.actions.docker_ops import register_docker_ops
    from app.actions.file_ops import register_file_ops
    from app.actions.git_ops import register_git_ops

    registry = ActionRegistry()
    for name, desc, risk in _ACTION_METADATA:
        registry.register(ActionMeta(
            name=name,
            description=desc,
            risk_level=risk,
            requires_approval=(risk != "low"),
            handler=_ACTIONS[name],  # type: ignore[arg-type]
        ))

    allowed_roots = (settings.project_dir, settings.terminal_workdir)
    register_file_ops(registry, allowed_roots=allowed_roots)
    register_git_ops(registry, project_dir=settings.project_dir)
    register_docker_ops(registry, project_dir=settings.project_dir)

    from app.actions.deploy import register_deploy_actions
    health_url = str(settings.app_url).rstrip("/") + "/health" if settings.app_url else ""
    register_deploy_actions(registry, project_dir=settings.project_dir, health_url=health_url)

    if settings.enable_github and settings.github_token and settings.github_repo:
        from app.actions.github_ops import register_github_ops
        from app.adapters.github import GitHubAdapter, GitHubUnavailableError
        try:
            gh = GitHubAdapter(
                token=settings.github_token,
                repo=settings.github_repo,
            )
            register_github_ops(registry, github=gh)
        except GitHubUnavailableError:
            pass

    return registry


action_registry: ActionRegistry = _build_registry()
