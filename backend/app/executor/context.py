"""ContextCollector — collect environment snapshot for injection into LLM prompts.

Mengumpulkan informasi repo + infrastruktur (git, docker, hostname, dsb.)
dan meng-cache hasilnya selama 30 detik supaya tidak flood subprocess tiap
request dalam burst.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_CACHE_TTL_SECONDS: int = 30
_SUBPROCESS_TIMEOUT: int = 8


def _run_quietly(args: list[str], cwd: Path | None = None) -> str:
    """Run subprocess, return stdout+stderr merged. Never raises."""
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
            check=False,
        )
        return result.stdout.strip()
    except FileNotFoundError:
        return f"(command not found: {args[0]})"
    except subprocess.TimeoutExpired:
        return f"(timeout after {_SUBPROCESS_TIMEOUT}s)"
    except OSError as exc:
        return f"(error: {exc})"


@dataclass(frozen=True)
class EnvironmentContext:
    """Snapshot of the environment at a point in time."""

    git_status: str
    docker_ps: str
    repo_files: str       # git ls-files HEAD, first 50 lines
    hostname: str
    working_dir: str
    collected_at: datetime = field(default_factory=datetime.now)

    def render(self) -> str:
        """Render as a human-readable block for injection into LLM prompts."""
        return (
            f"Hostname: {self.hostname}\n"
            f"Working dir: {self.working_dir}\n\n"
            f"Git status:\n{self.git_status or '(no git repo)'}\n\n"
            f"Docker containers:\n{self.docker_ps or '(docker not available)'}\n\n"
            f"Repository files (up to 50):\n{self.repo_files or '(not a git repo)'}\n"
        )


@dataclass
class _CachedEntry:
    context: EnvironmentContext
    expires_at: float


class ContextCollector:
    """Collect and cache environment context for LLM prompt injection."""

    def __init__(self, working_dir: Path, ttl_seconds: int = _CACHE_TTL_SECONDS) -> None:
        self._working_dir = working_dir
        self._ttl = ttl_seconds
        self._cache: _CachedEntry | None = None

    def collect(self) -> EnvironmentContext:
        """Return cached context if still fresh, else re-collect."""
        now = time.monotonic()
        if self._cache is not None and now < self._cache.expires_at:
            return self._cache.context

        context = self._collect_fresh()
        self._cache = _CachedEntry(context=context, expires_at=now + self._ttl)
        return context

    def invalidate(self) -> None:
        """Force re-collection on next call (e.g. after a git pull)."""
        self._cache = None

    def _collect_fresh(self) -> EnvironmentContext:
        cwd = self._working_dir

        hostname = _run_quietly(["hostname"])
        git_status = _run_quietly(["git", "status", "--short"], cwd=cwd)

        # List tracked+untracked files via git, cap at 50 lines.
        raw_files = _run_quietly(
            ["git", "ls-files", "--others", "--cached", "--exclude-standard"],
            cwd=cwd,
        )
        repo_files = "\n".join(raw_files.splitlines()[:50])

        # docker ps — compact columns only
        docker_ps = _run_quietly([
            "docker", "ps",
            "--format", "table {{.Names}}\t{{.Status}}\t{{.Image}}",
        ])

        return EnvironmentContext(
            git_status=git_status,
            docker_ps=docker_ps,
            repo_files=repo_files,
            hostname=hostname,
            working_dir=str(cwd),
            collected_at=datetime.now(),
        )
