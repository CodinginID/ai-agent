from __future__ import annotations

import os
import platform
import socket
import time
from pathlib import Path
from typing import Any

import psutil

from app.config import settings
from app.handlers.formatting import bytes_to_gb
from app.handlers.process_runners import run_process


def safe_psutil(read_metric: Any, default: Any = None) -> Any:
    try:
        return read_metric()
    except Exception:
        return default


def action_server_status(_: dict | None = None) -> str:
    boot_time = safe_psutil(psutil.boot_time)
    memory = safe_psutil(psutil.virtual_memory)
    disk = safe_psutil(lambda: psutil.disk_usage("/"))
    load_avg = os.getloadavg() if hasattr(os, "getloadavg") else None
    load_text = ", ".join(f"{value:.2f}" for value in load_avg) if load_avg else "N/A"
    cpu_percent = safe_psutil(lambda: psutil.cpu_percent(interval=1), "N/A")

    lines = [
        "Server status",
        f"Host: {socket.gethostname()}",
        f"OS: {platform.platform()}",
    ]

    if boot_time:
        boot_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(boot_time))
        uptime_seconds = int(time.time() - boot_time)
        uptime_hours = uptime_seconds // 3600
        uptime_minutes = (uptime_seconds % 3600) // 60
        lines.append(f"Boot: {boot_at}")
        lines.append(f"Uptime: {uptime_hours} jam {uptime_minutes} menit")
    else:
        lines.append("Boot: N/A")
        lines.append("Uptime: N/A")

    if isinstance(cpu_percent, (int, float)):
        lines.append(f"CPU: {cpu_percent:.1f}%")
    else:
        lines.append(f"CPU: {cpu_percent}")

    lines.append(f"Load average: {load_text}")

    if memory:
        lines.append(
            f"RAM: {memory.percent:.1f}% ({bytes_to_gb(memory.used)} / {bytes_to_gb(memory.total)})"
        )
    else:
        lines.append("RAM: N/A")

    if disk:
        lines.append(
            f"Disk /: {disk.percent:.1f}% ({bytes_to_gb(disk.used)} / {bytes_to_gb(disk.total)})"
        )
    else:
        lines.append("Disk /: N/A")

    return "\n".join(lines)


def action_memory(_: dict | None = None) -> str:
    memory = safe_psutil(psutil.virtual_memory)
    swap = safe_psutil(psutil.swap_memory)
    if not memory:
        return "Gagal membaca informasi memory."

    swap_used = bytes_to_gb(swap.used) if swap else "N/A"
    swap_total = bytes_to_gb(swap.total) if swap else "N/A"
    swap_percent = f"{swap.percent:.1f}%" if swap else "N/A"

    return "\n".join(
        [
            "Memory",
            f"RAM total: {bytes_to_gb(memory.total)}",
            f"RAM used: {bytes_to_gb(memory.used)} ({memory.percent:.1f}%)",
            f"RAM available: {bytes_to_gb(memory.available)}",
            f"Swap used: {swap_used} / {swap_total} ({swap_percent})",
        ]
    )


def action_disk(_: dict | None = None) -> str:
    lines = ["Disk usage"]
    partitions = safe_psutil(lambda: psutil.disk_partitions(all=False), [])
    seen_mountpoints: set[str] = set()
    for partition in partitions:
        mp = partition.mountpoint
        # Container bind mounts (mis. /etc/resolv.conf) terdeteksi sebagai
        # "partition" oleh psutil. Filter: hanya direktori real yang dihitung.
        if not Path(mp).is_dir():
            continue
        # Mountpoint yang sama bisa muncul beberapa kali kalau ada bind mount
        # nested — dedup supaya tidak nampilkan duplicate.
        if mp in seen_mountpoints:
            continue
        seen_mountpoints.add(mp)
        try:
            usage = psutil.disk_usage(mp)
        except (PermissionError, OSError):
            continue
        lines.append(
            f"{mp}: {usage.percent:.1f}% "
            f"({bytes_to_gb(usage.used)} / {bytes_to_gb(usage.total)})"
        )

    if len(lines) == 1:
        return run_process(["df", "-h"])

    return "\n".join(lines)


def action_processes(_: dict | None = None) -> str:
    processes = []
    try:
        iterator = psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent"])
        for proc in iterator:
            try:
                info = proc.info
            except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
                continue

            processes.append(
                (
                    info.get("cpu_percent") or 0,
                    info.get("memory_percent") or 0,
                    info.get("pid"),
                    info.get("name") or "-",
                    info.get("username") or "-",
                )
            )
    except Exception:
        return run_process(["ps", "aux"])

    if not processes:
        return run_process(["ps", "aux"])

    rows = ["Top processes", "CPU%   MEM%   PID     NAME                 USER"]
    for cpu, mem, pid, name, username in sorted(processes, reverse=True)[:15]:
        rows.append(f"{cpu:>5.1f}  {mem:>5.1f}  {pid:<7} {name[:20]:<20} {username[:18]}")

    return "\n".join(rows)


def action_docker_ps(_: dict | None = None) -> str:
    return run_process(["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"])


def action_docker_images(_: dict | None = None) -> str:
    return run_process(["docker", "images"])


def action_docker_stats(_: dict | None = None) -> str:
    return run_process(["docker", "stats", "--no-stream"])


def _project_dir(context: dict | None) -> Path:
    if context and "project_dir" in context:
        return Path(context["project_dir"]).expanduser().resolve()
    return settings.project_dir


def action_git_status(context: dict | None = None) -> str:
    return run_process(["git", "status", "--short", "--branch"], cwd=_project_dir(context))


def action_list_files(context: dict | None = None) -> str:
    return run_process(["ls", "-lah"], cwd=_project_dir(context))


def action_whoami(context: dict | None = None) -> str:
    lines = []
    telegram_user = (context or {}).get("telegram_user")
    if telegram_user:
        lines.extend(
            [
                f"Telegram user ID: {telegram_user['id']}",
                f"Username: {telegram_user['username']}",
                f"Admin restriction: {'nonaktif' if settings.allow_unrestricted_access else 'aktif'}",
                "",
            ]
        )

    project_dir = _project_dir(context)
    lines.extend(
        [
            f"Bot user: {run_process(['whoami'])}",
            f"Working dir: {project_dir}",
            f"Hostname: {socket.gethostname()}",
        ]
    )
    return "\n".join(lines)
