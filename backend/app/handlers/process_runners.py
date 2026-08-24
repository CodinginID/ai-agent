from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import settings
from app.executor.runner import run_safe
from app.handlers.formatting import format_output


def run_process(args: list[str], cwd: Path | None = None) -> str:
    output, _ = run_safe(args, cwd=cwd or settings.project_dir, timeout=settings.command_timeout)
    return format_output(output)


def run_agent_process(args: list[str], cwd: Path | None = None) -> str:
    workdir = cwd or settings.agent_workdir
    if not workdir.exists():
        return f"Agent workdir tidak ditemukan: {workdir}"

    try:
        result = subprocess.run(
            args,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=settings.agent_timeout,
            check=False,
        )
    except FileNotFoundError:
        return f"Agent command tidak ditemukan: {args[0]}"
    except subprocess.TimeoutExpired:
        return f"Agent timeout setelah {settings.agent_timeout} detik."

    output = result.stdout.strip()
    if result.returncode != 0:
        output = f"Exit code: {result.returncode}\n{output}"

    return format_output(output)


def run_terminal_process(args: list[str], cwd: Path | None = None) -> str:
    import os

    workdir = cwd or settings.terminal_workdir
    if not workdir.exists():
        return f"Terminal workdir tidak ditemukan: {workdir}"

    env = os.environ.copy()
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("NO_COLOR", "1")

    try:
        result = subprocess.run(
            args,
            cwd=str(workdir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=settings.terminal_timeout,
            check=False,
        )
    except FileNotFoundError:
        return f"Command tidak ditemukan: {args[0]}"
    except subprocess.TimeoutExpired:
        return f"Command timeout setelah {settings.terminal_timeout} detik."

    output = result.stdout.strip()
    if result.returncode != 0:
        output = f"Exit code: {result.returncode}\n{output}"

    return format_output(output)
