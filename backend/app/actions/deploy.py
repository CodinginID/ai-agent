"""Deploy workflow actions — orchestrate git pull + compose build/up + health check."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests  # type: ignore[import-untyped]

from app.executor.actions import ActionMeta, ActionProtocol, ActionRegistry
from app.executor.runner import run_safe


@dataclass
class ServiceHealthCheckAction:
    """Check if a service HTTP endpoint is responding."""

    @property
    def name(self) -> str:
        return "service_health_check"

    @property
    def description(self) -> str:
        return "Check if a service URL is responding. Params: url (str)"

    def execute(self, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        url = str(params.get("url", "")).strip()
        if not url:
            return "Error: parameter 'url' wajib diisi."
        if not url.startswith(("http://", "https://")):
            return "Error: URL harus diawali dengan http:// atau https://"

        try:
            resp = requests.get(url, timeout=10, allow_redirects=True)
            elapsed = resp.elapsed.total_seconds()
            if resp.ok:
                return f"✅ UP — {url} → {resp.status_code} ({elapsed:.2f}s)"
            return f"⚠️ {resp.status_code} — {url} ({elapsed:.2f}s)"
        except requests.ConnectionError:
            return f"❌ DOWN — cannot connect to {url}"
        except requests.Timeout:
            return f"❌ TIMEOUT — {url} did not respond within 10s"
        except Exception as exc:
            return f"❌ Health check gagal: {exc}"


@dataclass
class DeployAction:
    """Full deploy sequence: git pull → compose build → compose up → health check.

    Captures pre-deploy HEAD so a rollback plan can be generated after execution.
    Output includes the pre-deploy commit hash on a dedicated line:
    ``pre_deploy_commit: <hash>``
    """

    project_dir: Path = field(default_factory=Path)
    health_url: str = ""

    @property
    def name(self) -> str:
        return "deploy"

    @property
    def description(self) -> str:
        return "Full deploy: git pull + docker compose build + up + health check. Params: no_cache (bool)"

    def execute(self, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        lines: list[str] = []

        # Capture pre-deploy commit for rollback
        pre_commit, _ = run_safe(["git", "rev-parse", "HEAD"], cwd=self.project_dir)
        pre_commit = pre_commit.strip()
        lines.append(f"pre_deploy_commit: {pre_commit}")

        # 1. git pull
        pull_out, pull_rc = run_safe(
            ["git", "pull", "origin"],
            cwd=self.project_dir,
            timeout=60,
        )
        lines.append(f"\n[1/4] git pull\n{pull_out or 'Already up to date.'}")
        if pull_rc != 0:
            lines.append("❌ git pull gagal — deploy dibatalkan.")
            return "\n".join(lines)

        # 2. docker compose build
        build_cmd = ["docker", "compose", "build"]
        if params.get("no_cache"):
            build_cmd.append("--no-cache")
        build_out, build_rc = run_safe(build_cmd, cwd=self.project_dir, timeout=300)
        lines.append(f"\n[2/4] docker compose build\n{build_out or 'Build selesai.'}")
        if build_rc != 0:
            lines.append("❌ Build gagal — deploy dibatalkan.")
            return "\n".join(lines)

        # 3. docker compose up
        up_out, up_rc = run_safe(
            ["docker", "compose", "up", "-d", "--remove-orphans"],
            cwd=self.project_dir,
            timeout=120,
        )
        lines.append(f"\n[3/4] docker compose up\n{up_out or 'Services started.'}")
        if up_rc != 0:
            lines.append("❌ compose up gagal.")
            return "\n".join(lines)

        # 4. optional health check
        if self.health_url:
            hc = ServiceHealthCheckAction().execute({"url": self.health_url})
            lines.append(f"\n[4/4] health check\n{hc}")
        else:
            lines.append("\n[4/4] health check — dikonfigurasi via APP_URL")

        lines.append(f"\n✅ Deploy selesai. Rollback ke: {pre_commit[:8]}")
        return "\n".join(lines)


def register_deploy_actions(
    registry: ActionRegistry,
    project_dir: Path,
    health_url: str = "",
) -> None:
    """Register deploy and health check actions into *registry*."""
    actions: list[ActionProtocol] = [
        ServiceHealthCheckAction(),
        DeployAction(project_dir=project_dir, health_url=health_url),
    ]

    risk_map: dict[str, str] = {
        "service_health_check": "low",
        "deploy":               "high",
    }

    for action in actions:
        risk = risk_map.get(action.name, "high")
        registry.register(ActionMeta(
            name=action.name,
            description=action.description,
            risk_level=risk,
            requires_approval=(risk == "high"),
            handler=action.execute,
        ))
