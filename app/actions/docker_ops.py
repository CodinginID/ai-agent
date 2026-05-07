"""Extended Docker actions — logs, restart, stats, build, exec."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.executor.actions import ActionMeta, ActionRegistry
from app.executor.runner import run_safe

# Container / image names must not contain shell-unsafe characters.
_SAFE_NAME_RE: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-/:]*$")


class DockerOperationError(Exception):
    """Docker command failed or an argument is invalid."""


def _validate_container_name(name: str) -> str | None:
    """Return error message if *name* is not a safe container/image identifier."""
    if not name:
        return "Nama container wajib diisi."
    if not _SAFE_NAME_RE.match(name):
        return f"Nama container tidak valid: {name!r}"
    return None


@dataclass
class DockerLogsAction:
    """Get container logs."""

    @property
    def name(self) -> str:
        return "docker_logs"

    @property
    def description(self) -> str:
        return "Get container logs. Params: container (str), tail (int, default 50)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        container = str(params.get("container", "")).strip()
        err = _validate_container_name(container)
        if err:
            return f"Error: {err}"

        try:
            tail = int(params.get("tail", 50))
        except (TypeError, ValueError):
            tail = 50
        tail = max(1, min(tail, 500))

        output, _ = run_safe(
            ["docker", "logs", "--tail", str(tail), container]
        )
        return output


@dataclass
class DockerRestartAction:
    """Restart a container."""

    @property
    def name(self) -> str:
        return "docker_restart"

    @property
    def description(self) -> str:
        return "Restart container. Params: container (str)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        container = str(params.get("container", "")).strip()
        err = _validate_container_name(container)
        if err:
            return f"Error: {err}"

        output, returncode = run_safe(["docker", "restart", container])
        if returncode != 0:
            return f"docker restart gagal:\n{output}"
        return f"Container '{container}' berhasil di-restart."


@dataclass
class DockerStatsAction:
    """Get container resource usage."""

    @property
    def name(self) -> str:
        return "docker_stats"

    @property
    def description(self) -> str:
        return "Get container stats (CPU/RAM). No additional params."

    def execute(self, params: dict | None = None) -> str:
        output, _ = run_safe(["docker", "stats", "--no-stream"])
        return output


@dataclass
class DockerBuildAction:
    """Build a Docker image."""

    project_dir: Path = field(default_factory=Path)

    @property
    def name(self) -> str:
        return "docker_build"

    @property
    def description(self) -> str:
        return "Build Docker image. Params: tag (str), context (str, default '.')"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        tag = str(params.get("tag", "")).strip()
        context_path = str(params.get("context", ".")).strip() or "."

        if not tag:
            return "Error: parameter 'tag' wajib diisi."
        if not _SAFE_NAME_RE.match(tag):
            return f"Tag tidak valid: {tag!r}"

        # context is relative to project_dir — validate no traversal
        if ".." in Path(context_path).parts:
            return "Error: path traversal tidak diizinkan."

        output, returncode = run_safe(
            ["docker", "build", "-t", tag, context_path],
            cwd=self.project_dir,
        )
        if returncode != 0:
            return f"docker build gagal:\n{output}"
        return output or f"Image '{tag}' berhasil di-build."


@dataclass
class DockerExecAction:
    """Execute command in container."""

    @property
    def name(self) -> str:
        return "docker_exec"

    @property
    def description(self) -> str:
        return "Execute command in container. Params: container (str), command (str)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        container = str(params.get("container", "")).strip()
        command = str(params.get("command", "")).strip()

        err = _validate_container_name(container)
        if err:
            return f"Error: {err}"
        if not command:
            return "Error: parameter 'command' wajib diisi."

        # Split command string into a list to avoid shell=True
        import shlex
        try:
            cmd_parts = shlex.split(command)
        except ValueError as exc:
            return f"Command tidak valid: {exc}"

        output, returncode = run_safe(
            ["docker", "exec", container, *cmd_parts]
        )
        if returncode != 0:
            return f"docker exec gagal:\n{output}"
        return output


def register_docker_ops(registry: ActionRegistry, project_dir: Path) -> None:
    """Register all extended Docker actions into *registry*."""
    actions: list[object] = [
        DockerLogsAction(),
        DockerRestartAction(),
        DockerStatsAction(),
        DockerBuildAction(project_dir=project_dir),
        DockerExecAction(),
    ]

    risk_map: dict[str, str] = {
        "docker_logs":    "low",
        "docker_restart": "medium",
        "docker_stats":   "low",
        "docker_build":   "medium",
        "docker_exec":    "high",
    }

    for action in actions:
        # Each action object follows the informal Action protocol (name, description, execute)
        risk = risk_map.get(action.name, "medium")  # type: ignore[attr-defined]
        registry.register(ActionMeta(
            name=action.name,  # type: ignore[attr-defined]
            description=action.description,  # type: ignore[attr-defined]
            risk_level=risk,
            requires_approval=(risk == "high"),
            handler=action.execute,  # type: ignore[attr-defined]
        ))
