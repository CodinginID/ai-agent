from __future__ import annotations

import shlex

from app.config import settings
from app.handlers.actions import action_processes, action_server_status
from app.handlers.agents import agent_binary_status
from app.handlers.process_runners import run_terminal_process


def terminal_status_text() -> str:
    commands = sorted(settings.terminal_allowed_commands)
    lines = [
        "Terminal tools",
        f"Enabled: {settings.enable_terminal_tools}",
        f"Workdir: {settings.terminal_workdir}",
        f"Timeout: {settings.terminal_timeout}s",
        "",
        "Allowed commands:",
    ]

    for command in commands:
        lines.append(f"- {command}: {agent_binary_status(command)}")

    return "\n".join(lines)


def run_terminal_command(command_text: str) -> str:
    if not settings.enable_terminal_tools:
        return "Terminal tools belum aktif. Set ENABLE_TERMINAL_TOOLS=true di .env lalu restart bot."

    if not settings.admin_user_ids and not settings.allow_unrestricted_access:
        return "Isi ADMIN_USER_IDS di .env dulu sebelum mengaktifkan terminal tools dari Telegram."

    try:
        parts = shlex.split(command_text)
    except ValueError as exc:
        return f"Command tidak valid: {exc}"

    if not parts:
        return "Command kosong."

    command = parts[0]
    if command not in settings.terminal_allowed_commands:
        allowed = ", ".join(sorted(settings.terminal_allowed_commands))
        return f"Command tidak diizinkan: {command}\nAllowed: {allowed}"

    return run_terminal_process(parts)


def btop_snapshot() -> str:
    status = action_server_status({})
    processes = action_processes({})
    return (
        "btop adalah aplikasi TUI, jadi tidak bisa dibuka interaktif di Telegram.\n"
        "Ini snapshot server sebagai pengganti:\n\n"
        f"{status}\n\n{processes}"
    )


def spf_listing(path_text: str = "") -> str:
    path = (path_text or ".").strip()
    if not settings.enable_terminal_tools:
        return "Terminal tools belum aktif. Set ENABLE_TERMINAL_TOOLS=true di .env lalu restart bot."

    try:
        target = (settings.terminal_workdir / path).resolve()
    except ValueError as exc:
        return f"Path tidak valid: {exc}"

    try:
        target.relative_to(settings.terminal_workdir)
    except ValueError:
        return f"Path keluar dari TERMINAL_WORKDIR tidak diizinkan: {target}"

    if not target.exists():
        return f"Path tidak ditemukan: {target}"

    if target.is_file():
        return run_terminal_process(["ls", "-lah", str(target)], cwd=settings.terminal_workdir)

    return (
        "spf adalah aplikasi TUI, jadi tidak bisa dibuka interaktif di Telegram.\n"
        "Ini listing direktori sebagai pengganti:\n\n"
        f"{run_terminal_process(['ls', '-lah', str(target)], cwd=settings.terminal_workdir)}"
    )
