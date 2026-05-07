import asyncio
import contextlib
import json
import os
import platform
import shlex
import shutil
import socket
import subprocess
import time
from pathlib import Path

import psutil
import requests
from telegram import Update
from telegram.ext import ContextTypes

from app.adapters.agent_discovery import CliAgentDefinition, CliAgentDiscoveryAdapter
from app.adapters.database.repositories import ControlPlaneRepository, DatabaseConflictError
from app.adapters.database.session import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from app.config import BASE_DIR, settings
from app.domain.agents import AgentCapability, AgentRoleAssignment, resolve_agent_roles
from app.executor.actions import ActionMeta, ActionRegistry
from app.executor.runner import run_safe
from app.intents.parser import IntentParser
from app.intents.schemas import EXECUTABLE_ACTIONS
from app.memory.store import ProjectAlreadyExistsError, ProjectStore
from app.orchestrator.approval import PendingPlanStore
from app.orchestrator.plans import PlanGenerator

project_store = ProjectStore(BASE_DIR / "data")
plan_generator = PlanGenerator()
pending_plans = PendingPlanStore()

OLLAMA_HOST = settings.ollama_host

# DB session factory — lazy init saat /start pertama kali dipanggil
_db_session_factory = None


def _get_db_session_factory():
    global _db_session_factory
    if _db_session_factory is None:
        _db_session_factory = create_session_factory(
            create_database_engine(settings.database_url)
        )
    return _db_session_factory
QWEN_URL = settings.qwen_url
QWEN_MODEL = settings.qwen_model
PROJECT_DIR = settings.project_dir
COMMAND_TIMEOUT = settings.command_timeout
MAX_REPLY_CHARS = settings.max_reply_chars
CHAT_HISTORY_LIMIT = settings.chat_history_limit
ALLOW_UNRESTRICTED_ACCESS = settings.allow_unrestricted_access
ENABLE_CODEX = settings.enable_codex
ENABLE_CLAUDE = settings.enable_claude
AGENT_TIMEOUT = settings.agent_timeout
AGENT_WORKDIR = settings.agent_workdir
AGENT_MAX_PROMPT_CHARS = settings.agent_max_prompt_chars
CODEX_BIN = settings.codex_bin
CODEX_MODEL = settings.codex_model
CODEX_SANDBOX = settings.codex_sandbox
CLAUDE_BIN = settings.claude_bin
CLAUDE_MODEL = settings.claude_model
CLAUDE_PERMISSION_MODE = settings.claude_permission_mode
CLAUDE_ALLOWED_TOOLS = settings.claude_allowed_tools
CLAUDE_TOOLS = settings.claude_tools
ENABLE_GLM = settings.enable_glm
GLM_BIN = settings.glm_bin
GLM_MODEL = settings.glm_model
GLM_ACCESS_MODE = settings.glm_access_mode
AGENT_ROLE_ENGINEER = settings.agent_role_engineer
AGENT_ROLE_ARCHITECT = settings.agent_role_architect
AGENT_ROLE_REVIEWER = settings.agent_role_reviewer
ENABLE_TERMINAL_TOOLS = settings.enable_terminal_tools
TERMINAL_TIMEOUT = settings.terminal_timeout
TERMINAL_WORKDIR = settings.terminal_workdir
TERMINAL_ALLOWED_COMMANDS = settings.terminal_allowed_commands
ADMIN_USER_IDS = settings.admin_user_ids
ALLOWED_MANUAL_COMMANDS = settings.allowed_manual_commands

VALID_CODEX_SANDBOXES = {"read-only", "workspace-write", "danger-full-access"}
CODEX_SANDBOX_ALIASES = {
    "readonly": "read-only",
    "read_only": "read-only",
    "seatbelt": "read-only",
    "sandbox": "read-only",
    "workspace": "workspace-write",
    "full": "danger-full-access",
    "full-access": "danger-full-access",
    "danger": "danger-full-access",
}


def is_authorized(update: Update) -> bool:
    if ALLOW_UNRESTRICTED_ACCESS:
        return True

    user = update.effective_user
    return bool(user and user.id in ADMIN_USER_IDS)


def format_telegram_user(update: Update) -> str:
    user = update.effective_user
    username = f"@{user.username}" if user and user.username else "-"
    return "\n".join(
        [
            f"Telegram user ID: {user.id if user else '-'}",
            f"Username: {username}",
            f"Admin restriction: {'nonaktif' if ALLOW_UNRESTRICTED_ACCESS else 'aktif'}",
        ]
    )


def format_output(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "(no output)"

    if len(text) <= MAX_REPLY_CHARS:
        return text

    return text[:MAX_REPLY_CHARS] + "\n\n...output dipotong..."


def call_qwen(prompt: str) -> str:
    response = requests.post(
        QWEN_URL,
        json={
            "model": QWEN_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["response"].strip()


def run_process(args: list[str], cwd: Path | None = None) -> str:
    output, _ = run_safe(args, cwd=cwd or PROJECT_DIR, timeout=COMMAND_TIMEOUT)
    return format_output(output)


def run_agent_process(args: list[str], cwd: Path | None = None) -> str:
    workdir = cwd or AGENT_WORKDIR
    if not workdir.exists():
        return f"Agent workdir tidak ditemukan: {workdir}"

    try:
        result = subprocess.run(
            args,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=AGENT_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return f"Agent command tidak ditemukan: {args[0]}"
    except subprocess.TimeoutExpired:
        return f"Agent timeout setelah {AGENT_TIMEOUT} detik."
    except Exception as exc:
        return f"Gagal menjalankan agent: {exc}"

    output = result.stdout.strip()
    if result.returncode != 0:
        output = f"Exit code: {result.returncode}\n{output}"

    return format_output(output)


def run_terminal_process(args: list[str], cwd: Path | None = None) -> str:
    workdir = cwd or TERMINAL_WORKDIR
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
            timeout=TERMINAL_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return f"Command tidak ditemukan: {args[0]}"
    except subprocess.TimeoutExpired:
        return f"Command timeout setelah {TERMINAL_TIMEOUT} detik."
    except Exception as exc:
        return f"Gagal menjalankan terminal tool: {exc}"

    output = result.stdout.strip()
    if result.returncode != 0:
        output = f"Exit code: {result.returncode}\n{output}"

    return format_output(output)


def validate_agent_prompt(prompt: str) -> str | None:
    if not prompt.strip():
        return "Prompt kosong."

    if len(prompt) > AGENT_MAX_PROMPT_CHARS:
        return f"Prompt terlalu panjang. Maksimal {AGENT_MAX_PROMPT_CHARS} karakter."

    if not ADMIN_USER_IDS and not ALLOW_UNRESTRICTED_ACCESS:
        return "Isi ADMIN_USER_IDS di .env dulu sebelum mengaktifkan akses Codex/Claude dari Telegram."

    return None


def build_agent_prompt(user_prompt: str, agent_name: str) -> str:
    access_mode = (
        f"Codex sandbox={normalized_codex_sandbox() or CODEX_SANDBOX}"
        if agent_name == "Codex"
        else f"Claude permission={CLAUDE_PERMISSION_MODE}, tools={CLAUDE_TOOLS or CLAUDE_ALLOWED_TOOLS or 'default'}"
    )
    return f"""
Kamu sedang dipanggil dari private Telegram bot untuk membantu user mengelola project/server.

Agent: {agent_name}
Working directory: {AGENT_WORKDIR}
Access mode: {access_mode}

Aturan respons:
- Jawab dalam bahasa user.
- Buat output ringkas dan cocok untuk Telegram.
- Jika akses edit tersedia dan user meminta edit, lakukan perubahan langsung.
- Jika environment/tool tidak punya izin edit, jelaskan batasannya.
- Jangan meminta input interaktif karena sesi ini non-interactive.

Instruksi user:
{user_prompt}
""".strip()


def agent_binary_status(binary_name: str) -> str:
    binary_path = shutil.which(binary_name)
    return binary_path or "tidak ditemukan di PATH"


def normalized_codex_sandbox() -> str | None:
    sandbox = CODEX_SANDBOX.strip().lower()
    sandbox = CODEX_SANDBOX_ALIASES.get(sandbox, sandbox)
    if sandbox not in VALID_CODEX_SANDBOXES:
        return None

    return sandbox


def run_codex_agent(prompt: str) -> str:
    validation_error = validate_agent_prompt(prompt)
    if validation_error:
        return validation_error

    if not ENABLE_CODEX:
        return "Codex belum aktif. Set ENABLE_CODEX=true di .env lalu restart bot."

    codex_path = shutil.which(CODEX_BIN)
    if not codex_path:
        return f"Codex CLI tidak ditemukan: {CODEX_BIN}"

    sandbox = normalized_codex_sandbox()
    if not sandbox:
        allowed = ", ".join(sorted(VALID_CODEX_SANDBOXES))
        return f"CODEX_SANDBOX tidak valid: {CODEX_SANDBOX}. Allowed: {allowed}"

    args = [
        codex_path,
        "exec",
        "--cd",
        str(AGENT_WORKDIR),
        "--sandbox",
        sandbox,
        "--ask-for-approval",
        "never",
        "--skip-git-repo-check",
        "--ephemeral",
        "--color",
        "never",
    ]
    if CODEX_MODEL:
        args.extend(["--model", CODEX_MODEL])

    args.append(build_agent_prompt(prompt, "Codex"))
    return run_agent_process(args)


def run_claude_agent(prompt: str) -> str:
    validation_error = validate_agent_prompt(prompt)
    if validation_error:
        return validation_error

    if not ENABLE_CLAUDE:
        return "Claude belum aktif. Set ENABLE_CLAUDE=true di .env lalu restart bot."

    claude_path = shutil.which(CLAUDE_BIN)
    if not claude_path:
        return f"Claude CLI tidak ditemukan: {CLAUDE_BIN}"

    args = [
        claude_path,
        "--print",
        "--no-session-persistence",
        "--permission-mode",
        CLAUDE_PERMISSION_MODE,
        "--output-format",
        "text",
    ]
    if CLAUDE_TOOLS:
        args.extend(["--tools", CLAUDE_TOOLS])
    if CLAUDE_ALLOWED_TOOLS and CLAUDE_ALLOWED_TOOLS.lower() != "default":
        args.extend(["--allowedTools", CLAUDE_ALLOWED_TOOLS])
    if CLAUDE_MODEL:
        args.extend(["--model", CLAUDE_MODEL])

    args.append(build_agent_prompt(prompt, "Claude"))
    return run_agent_process(args)


def qwen_capability() -> AgentCapability:
    return AgentCapability(
        agent_id="qwen",
        display_name="Qwen/Ollama",
        provider="ollama",
        role_hint="orchestrator",
        enabled=True,
        available=bool(QWEN_URL and QWEN_MODEL),
        path=QWEN_URL,
        model=QWEN_MODEL,
        access_mode="controller-only",
        description="Orchestrator, intent parser, planner, and result analyzer",
    )


def discover_agent_capabilities() -> tuple[AgentCapability, ...]:
    cli_agents = (
        CliAgentDefinition(
            agent_id="codex",
            display_name="Codex",
            provider="openai",
            role_hint="engineer",
            executable=CODEX_BIN,
            enabled=ENABLE_CODEX,
            model=CODEX_MODEL or None,
            access_mode=normalized_codex_sandbox() or CODEX_SANDBOX,
            description="Code editing and engineering worker",
        ),
        CliAgentDefinition(
            agent_id="claude",
            display_name="Claude",
            provider="anthropic",
            role_hint="reviewer",
            executable=CLAUDE_BIN,
            enabled=ENABLE_CLAUDE,
            model=CLAUDE_MODEL or None,
            access_mode=f"permission={CLAUDE_PERMISSION_MODE}, tools={CLAUDE_TOOLS or CLAUDE_ALLOWED_TOOLS or 'default'}",
            description="Review and code reasoning worker",
        ),
        CliAgentDefinition(
            agent_id="glm",
            display_name="GLM",
            provider="zhipu",
            role_hint="architect",
            executable=GLM_BIN,
            enabled=ENABLE_GLM,
            model=GLM_MODEL or None,
            access_mode=GLM_ACCESS_MODE,
            description="Architecture and planning worker",
        ),
    )
    discovered = CliAgentDiscoveryAdapter(cli_agents).discover()
    return (qwen_capability(), *discovered)


def agent_role_assignments(capabilities: tuple[AgentCapability, ...]) -> tuple[AgentRoleAssignment, ...]:
    return resolve_agent_roles(
        capabilities=capabilities,
        assignments={
            "orchestrator": "qwen",
            "engineer": AGENT_ROLE_ENGINEER,
            "architect": AGENT_ROLE_ARCHITECT,
            "reviewer": AGENT_ROLE_REVIEWER,
        },
    )


def format_agent_capability(capability: AgentCapability) -> list[str]:
    location = capability.path or "not found"
    enabled = "yes" if capability.enabled else "no"
    available = "yes" if capability.available else "no"
    lines = [
        f"- {capability.display_name} ({capability.agent_id}): {capability.status}",
        f"  provider: {capability.provider}",
        f"  role hint: {capability.role_hint}",
        f"  enabled: {enabled}",
        f"  available: {available}",
        f"  location: {location}",
    ]
    if capability.model:
        lines.append(f"  model: {capability.model}")
    if capability.access_mode:
        lines.append(f"  access: {capability.access_mode}")
    return lines


def agent_status_text() -> str:
    capabilities = discover_agent_capabilities()
    assignments = agent_role_assignments(capabilities)
    lines = [
        "Agent registry",
        f"Admin restriction: {'nonaktif' if ALLOW_UNRESTRICTED_ACCESS else 'aktif'}",
        f"Agent workdir: {AGENT_WORKDIR}",
        f"Agent timeout: {AGENT_TIMEOUT}s",
        "",
        "Role assignments:",
    ]

    for assignment in assignments:
        marker = "ready" if assignment.ready else "not ready"
        lines.append(f"- {assignment.role}: {assignment.agent_id} ({marker}, {assignment.status})")
        lines.append(f"  detail: {assignment.detail}")

    lines.extend(["", "Registered agents:"])
    for capability in capabilities:
        lines.extend(format_agent_capability(capability))

    return "\n".join(lines)


def terminal_status_text() -> str:
    commands = sorted(TERMINAL_ALLOWED_COMMANDS)
    lines = [
        "Terminal tools",
        f"Enabled: {ENABLE_TERMINAL_TOOLS}",
        f"Workdir: {TERMINAL_WORKDIR}",
        f"Timeout: {TERMINAL_TIMEOUT}s",
        "",
        "Allowed commands:",
    ]

    for command in commands:
        lines.append(f"- {command}: {agent_binary_status(command)}")

    return "\n".join(lines)


def run_terminal_command(command_text: str) -> str:
    if not ENABLE_TERMINAL_TOOLS:
        return "Terminal tools belum aktif. Set ENABLE_TERMINAL_TOOLS=true di .env lalu restart bot."

    if not ADMIN_USER_IDS and not ALLOW_UNRESTRICTED_ACCESS:
        return "Isi ADMIN_USER_IDS di .env dulu sebelum mengaktifkan terminal tools dari Telegram."

    try:
        parts = shlex.split(command_text)
    except ValueError as exc:
        return f"Command tidak valid: {exc}"

    if not parts:
        return "Command kosong."

    command = parts[0]
    if command not in TERMINAL_ALLOWED_COMMANDS:
        allowed = ", ".join(sorted(TERMINAL_ALLOWED_COMMANDS))
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
    if not ENABLE_TERMINAL_TOOLS:
        return "Terminal tools belum aktif. Set ENABLE_TERMINAL_TOOLS=true di .env lalu restart bot."

    try:
        target = (TERMINAL_WORKDIR / path).resolve()
    except Exception as exc:
        return f"Path tidak valid: {exc}"

    try:
        target.relative_to(TERMINAL_WORKDIR)
    except ValueError:
        return f"Path keluar dari TERMINAL_WORKDIR tidak diizinkan: {target}"

    if not target.exists():
        return f"Path tidak ditemukan: {target}"

    if target.is_file():
        return run_terminal_process(["ls", "-lah", str(target)], cwd=TERMINAL_WORKDIR)

    return (
        "spf adalah aplikasi TUI, jadi tidak bisa dibuka interaktif di Telegram.\n"
        "Ini listing direktori sebagai pengganti:\n\n"
        f"{run_terminal_process(['ls', '-lah', str(target)], cwd=TERMINAL_WORKDIR)}"
    )


def bytes_to_gb(value: int) -> str:
    return f"{value / (1024 ** 3):.2f} GB"


def safe_psutil(read_metric, default=None):
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
        lines.append(f"RAM: {memory.percent:.1f}% ({bytes_to_gb(memory.used)} / {bytes_to_gb(memory.total)})")
    else:
        lines.append("RAM: N/A")

    if disk:
        lines.append(f"Disk /: {disk.percent:.1f}% ({bytes_to_gb(disk.used)} / {bytes_to_gb(disk.total)})")
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
    return PROJECT_DIR


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
                f"Admin restriction: {'nonaktif' if ALLOW_UNRESTRICTED_ACCESS else 'aktif'}",
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


ACTIONS = {
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
            handler=ACTIONS[name],
        ))

    # Extended file operations
    allowed_roots = (PROJECT_DIR, TERMINAL_WORKDIR)
    register_file_ops(registry, allowed_roots=allowed_roots)

    # Extended git operations
    register_git_ops(registry, project_dir=PROJECT_DIR)

    # Extended docker operations
    register_docker_ops(registry, project_dir=PROJECT_DIR)

    # GitHub issues (only when explicitly enabled and configured)
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
            pass  # Misconfigured — skip silently; admin can check /tools

    return registry


action_registry = _build_registry()


intent_parser = IntentParser(qwen_caller=call_qwen)


def is_greeting(text: str) -> bool:
    greetings = {
        "hi", "hai", "halo", "hello", "hey",
        "pagi", "siang", "sore", "malam",
        "assalamualaikum", "assalamu'alaikum",
    }
    return text.lower().strip(" .,!?\n\t") in greetings


def looks_like_general_chat(text: str) -> bool:
    question_prefixes = (
        "apa itu",
        "apa maksud",
        "jelaskan",
        "explain",
        "what is",
        "what are",
        "bagaimana cara",
        "gimana cara",
        "kenapa",
        "mengapa",
        "why",
        "how to",
        "bantu",
        "bisa bantu",
        "bisa jelaskan",
        "tolong bantu",
        "tolong jelaskan",
    )
    action_keywords = (
        "cek",
        "check",
        "lihat",
        "tampilkan",
        "show",
        "status",
        "jalan",
        "running",
        "list",
        "daftar",
        "usage",
        "penggunaan",
        "stats",
        "statistik",
    )

    normalized = text.lower().strip()
    starts_as_question = normalized.endswith("?") or any(
        normalized.startswith(prefix) for prefix in question_prefixes
    )
    has_action_keyword = any(keyword in normalized for keyword in action_keywords)

    return starts_as_question and not has_action_keyword


def parse_intent_locally(user_text: str) -> dict:
    text = user_text.lower().strip()

    if is_greeting(text) or looks_like_general_chat(text):
        return {"action": "chat"}

    if "docker" in text or "container" in text:
        if "image" in text or "images" in text:
            return {"action": "docker_images"}
        if any(keyword in text for keyword in ["stats", "statistik", "resource", "cpu", "ram"]):
            return {"action": "docker_stats"}
        return {"action": "docker_ps"}

    if "git" in text:
        return {"action": "git_status"}

    if any(keyword in text for keyword in ["ram", "memory", "memori", "swap"]):
        return {"action": "memory"}

    if any(keyword in text for keyword in ["disk", "storage", "penyimpanan", "df"]):
        return {"action": "disk"}

    if any(keyword in text for keyword in ["process", "proses", "ps", "top"]):
        return {"action": "processes"}

    if any(keyword in text for keyword in ["whoami", "user bot", "hostname", "working dir"]):
        return {"action": "whoami"}

    if any(keyword in text for keyword in ["list file", "lihat file", "folder", "ls"]):
        return {"action": "list_files"}

    if any(keyword in text for keyword in ["status", "uptime", "health", "sehat", "server", "load", "cpu"]):
        return {"action": "server_status"}

    return {"action": "unknown"}


def parse_intent_with_ai(user_text: str) -> dict:
    local_intent = parse_intent_locally(user_text)
    if local_intent["action"] != "unknown":
        return local_intent

    prompt = f"""
You are an intent parser for a private Telegram server admin bot.

Choose exactly one action from this list:
- server_status: check server health, uptime, CPU, RAM, load, disk summary
- memory: check RAM or swap usage
- disk: check disk usage or storage
- processes: show active/top processes
- docker_ps: show running Docker containers
- docker_images: show Docker images
- docker_stats: show Docker container stats
- git_status: show git repository status
- list_files: list files in the project directory
- whoami: show bot user, working directory, and hostname
- chat: greetings, general conversation, explanations, or questions that should not execute server actions
- unknown: when the instruction does not match the available actions

User instruction:
{user_text}

Return only valid minified JSON with this shape:
{{"action":"server_status"}}
"""

    raw_response = call_qwen(prompt)
    json_start = raw_response.find("{")
    json_end = raw_response.rfind("}") + 1
    if json_start < 0 or json_end <= json_start:
        return {"action": "unknown"}

    try:
        data = json.loads(raw_response[json_start:json_end])
    except json.JSONDecodeError:
        return {"action": "unknown"}

    action = data.get("action")
    if action == "chat":
        return {"action": "chat"}

    if action not in ACTIONS:
        return {"action": "unknown"}

    return {"action": action}


def get_chat_history(context: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    return context.user_data.setdefault("chat_history", [])


def remember_chat(context: ContextTypes.DEFAULT_TYPE, user_text: str, assistant_text: str):
    history = get_chat_history(context)
    history.append(
        {
            "user": user_text,
            "assistant": assistant_text,
        }
    )
    del history[:-CHAT_HISTORY_LIMIT]


def build_chat_history_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    history = get_chat_history(context)
    if not history:
        return "(belum ada)"

    lines = []
    for item in history[-CHAT_HISTORY_LIMIT:]:
        lines.append(f"User: {item['user']}")
        lines.append(f"Assistant: {item['assistant']}")

    return "\n".join(lines)


def chat_with_qwen(user_text: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    history_text = build_chat_history_text(context)
    prompt = f"""
Kamu adalah AI-Agent App, asisten pribadi yang berjalan melalui Telegram.

Peran kamu:
- Menjawab sapaan, percakapan umum, dan pertanyaan teknis dengan natural.
- Gunakan bahasa yang sama dengan user. Jika user memakai Indonesia, jawab Indonesia.
- Jawab singkat, langsung, dan praktis.
- Jika user ingin menjalankan aksi server, arahkan ke contoh natural seperti "cek status server",
  "cek ram", "cek disk", "status docker", "git status", atau "/cmd docker ps".
- Jangan mengaku sudah menjalankan command server di mode chat. Eksekusi server hanya dilakukan
  oleh action bot, bukan oleh jawaban chat.

Riwayat chat terakhir:
{history_text}

User:
{user_text}

Assistant:
"""
    reply = call_qwen(prompt)
    remember_chat(context, user_text, reply)
    return reply


def run_manual_command(command_text: str) -> str:
    try:
        parts = shlex.split(command_text)
    except ValueError as exc:
        return f"Command tidak valid: {exc}"

    if not parts:
        return "Command kosong."

    command = parts[0]
    if command not in ALLOWED_MANUAL_COMMANDS:
        allowed = ", ".join(sorted(ALLOWED_MANUAL_COMMANDS))
        return f"Command tidak diizinkan: {command}\nAllowed: {allowed}"

    return run_process(parts)


async def deny_if_unauthorized(update: Update) -> bool:
    if is_authorized(update):
        return False

    await update.message.reply_text(
        "Akses ditolak. Kirim /whoami untuk melihat Telegram user ID, "
        "lalu masukkan ID itu ke ADMIN_USER_IDS di .env."
    )
    return True


_HELP_TEXT = (
    "Perintah yang tersedia:\n\n"
    "Chat natural:\n"
    "  cek status server\n"
    "  cek ram / cek disk\n"
    "  docker yang jalan apa aja\n"
    "  git status\n\n"
    "Agent CLI:\n"
    "  /agents — lihat agent terdaftar\n"
    "  /codex <instruksi>\n"
    "  /claude <instruksi>\n\n"
    "Terminal:\n"
    "  /tools — lihat tools aktif\n"
    "  /tool <command>\n\n"
    "Project:\n"
    "  /project — project aktif\n"
    "  /projects — daftar semua\n"
    "  /project_add <nama> <path>\n\n"
    "Lainnya:\n"
    "  /cmd <shell command>\n"
    "  /ask <pertanyaan>\n"
    "  /whoami — lihat Telegram ID\n"
    "  /reset — reset riwayat chat"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot ini private — hanya operator (di ADMIN_USER_IDS) yang bisa pakai.

    Fase A lockdown: hapus auto-register `/start` untuk siapapun. User asing
    yang nyasar dapat pesan halus. Operator pair via `/pair-telegram` di TUI.
    Pair code (``/start TG-XXX``) tetap diterima — tapi juga dibatasi whitelist.
    """
    if update.message is None or update.effective_user is None:
        return

    tg_user = update.effective_user
    args = context.args or []

    if not is_authorized(update):
        await update.message.reply_text(
            "Bot ini private — hanya bisa dipakai oleh pemilik server.\n\n"
            "Kalau kamu ingin install AI Agent untuk dirimu sendiri, "
            "deploy backend + bot Telegram sendiri. Lihat README di "
            "github.com/codinginid/ai-agent.",
        )
        return

    # /start TG-XXXXXX → klaim pair code (operator yang sudah login di TUI)
    if args and args[0].startswith("TG-"):
        await _handle_pair_code(update, tg_user, args[0])
        return

    # /start tanpa args → kasih instruksi, jangan auto-create user record.
    await update.message.reply_text(
        "Hai! Bot ini sudah aktif untuk akun kamu.\n\n"
        "Untuk hubungkan akun Telegram ini ke akun TUI:\n"
        "  1. Buka TUI di komputer kamu\n"
        "  2. Login Google dulu (`/login`)\n"
        "  3. Lalu `/pair-telegram` — scan QR atau klik link\n\n"
        + _HELP_TEXT
    )


async def _handle_pair_code(update: Update, tg_user, code: str) -> None:
    """Klaim code TUI pairing → link telegram_user_id ke user_id yang sudah login.

    Auto-merge ghost user: kalau telegram_user_id sudah ter-link ke user yang
    email=null (relik dari /start auto-register lama), hapus ghost user-nya
    lalu link ulang ke target user. Lebih ramah daripada nyuruh hubungi admin.
    """
    from sqlalchemy import select

    from app.adapters.database.models import UserModel
    from app.interfaces.auth import claim_telegram_pair_code

    user_id = claim_telegram_pair_code(code)
    if user_id is None:
        await update.message.reply_text(
            "Kode pair tidak valid atau sudah kedaluwarsa.\n"
            "Buka TUI di komputer dan jalankan /pair-telegram untuk dapat kode baru."
        )
        return

    try:
        with session_scope(_get_db_session_factory()) as session:
            repo = ControlPlaneRepository(session)
            existing = repo.resolve_by_telegram_user_id(tg_user.id)
            if existing is not None:
                if existing.user_id == user_id:
                    await update.message.reply_text(
                        "Akun Telegram kamu sudah ter-link ke user ini."
                    )
                    return
                # Cek apakah existing-nya ghost (email=null) → auto-merge.
                old_user = session.scalar(
                    select(UserModel).where(UserModel.id == existing.user_id)
                )
                if old_user is not None and not old_user.email:
                    session.delete(old_user)  # cascade: telegram_account ikut hilang
                    session.flush()
                else:
                    await update.message.reply_text(
                        "Akun Telegram kamu sudah ter-link ke user lain (yang punya email). "
                        "Hubungi admin untuk unlink dulu."
                    )
                    return
            repo.link_telegram_account(
                user_id=user_id,
                telegram_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )
    except DatabaseConflictError:
        await update.message.reply_text(
            "Akun Telegram kamu sudah ter-link ke user lain."
        )
        return
    except Exception as exc:
        await update.message.reply_text(f"Gagal link akun: {exc}")
        return

    await update.message.reply_text(
        "Berhasil terhubung. Kamu sekarang bisa pakai bot ini sebagai akun TUI kamu."
    )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_telegram_user(update))


async def cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    command_text = " ".join(context.args)
    output = run_manual_command(command_text)
    await update.message.reply_text(f"Command:\n{command_text}\n\nResult:\n{output}")


async def reply_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str):
    try:
        reply = chat_with_qwen(user_text, context)
    except requests.RequestException as exc:
        await update.message.reply_text(f"Gagal menghubungi Qwen/Ollama: {exc}")
        return
    except Exception as exc:
        await update.message.reply_text(f"Gagal membuat jawaban chat: {exc}")
        return

    await update.message.reply_text(format_output(reply))


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    question = " ".join(context.args).strip()
    if not question:
        await update.message.reply_text("Pakai format: /ask pertanyaan kamu")
        return

    await reply_chat(update, context, question)


async def agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Per-user agent config — list/toggle/set role/set model.

    Usage:
        /agents                       — list semua agent
        /agents <name> on|off         — enable/disable
        /agents <name> role <role>    — engineer/reviewer/architect
        /agents <name> model <model>  — override default model
    """
    if await deny_if_unauthorized(update):
        return

    tg_user = update.effective_user
    user_id = _resolve_user_id_from_telegram(tg_user.id if tg_user else None)
    if user_id is None:
        await update.message.reply_text(
            "Akun belum terdaftar. /start dulu, atau pair via /pair-telegram di TUI."
        )
        return

    from app.adapters.agent_configs import (
        DEFAULT_ROLE,
        KNOWN_AGENTS,
        VALID_ROLES,
        UserAgentConfigRepository,
    )

    repo = UserAgentConfigRepository(_get_db_session_factory())
    args = context.args or []

    if not args:
        existing = {c.agent_id: c for c in repo.list(user_id)}
        lines = ["Agent Config:"]
        for aid in KNOWN_AGENTS:
            cfg = existing.get(aid)
            en = "✓" if (cfg and cfg.enabled) else "✗"
            role = (cfg.role if cfg else None) or DEFAULT_ROLE.get(aid) or "-"
            model = (cfg.model if cfg else None) or "(default)"
            lines.append(f"  {en} {aid:<8} role={role:<10} model={model}")
        lines.append("")
        lines.append("Usage:")
        lines.append("  /agents codex on")
        lines.append("  /agents codex role engineer")
        lines.append("  /agents codex model gpt-4o-mini")
        await update.message.reply_text("\n".join(lines))
        return

    name = args[0].lower()
    if name not in KNOWN_AGENTS:
        await update.message.reply_text(
            f"Agent tidak dikenal: {name}. Allowed: {', '.join(KNOWN_AGENTS)}"
        )
        return
    if len(args) < 2:
        await update.message.reply_text(
            f"Usage: /agents {name} on|off | role <role> | model <model>"
        )
        return

    op = args[1].lower()
    try:
        if op in ("on", "off", "enable", "disable"):
            cfg = repo.upsert(user_id, name, enabled=(op in ("on", "enable")))
            await update.message.reply_text(
                f"✓ {cfg.agent_id}: enabled={cfg.enabled} role={cfg.role or '-'}"
            )
        elif op == "role" and len(args) >= 3:
            role = args[2].lower()
            if role not in VALID_ROLES:
                await update.message.reply_text(
                    f"Role invalid: {role}. Allowed: {', '.join(VALID_ROLES)}"
                )
                return
            cfg = repo.upsert(user_id, name, role=role)
            await update.message.reply_text(f"✓ {cfg.agent_id}: role={cfg.role}")
        elif op == "model" and len(args) >= 3:
            cfg = repo.upsert(user_id, name, model=args[2])
            await update.message.reply_text(f"✓ {cfg.agent_id}: model={cfg.model}")
        else:
            await update.message.reply_text(f"Op tidak dikenal: {op}")
    except Exception as exc:
        await update.message.reply_text(f"Gagal update: {exc}")


async def tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    await update.message.reply_text(format_output(terminal_status_text()))


async def tool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    command_text = " ".join(context.args).strip()
    if not command_text:
        await update.message.reply_text("Pakai format: /tool command args, contoh: /tool fastfetch")
        return

    result = await asyncio.to_thread(run_terminal_command, command_text)
    await update.message.reply_text(f"Tool result:\n\n{format_output(result)}")


async def btop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    result = await asyncio.to_thread(btop_snapshot)
    await update.message.reply_text(format_output(result))


async def spf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    path_text = " ".join(context.args).strip()
    result = await asyncio.to_thread(spf_listing, path_text)
    await update.message.reply_text(format_output(result))


async def codex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    prompt = " ".join(context.args).strip()
    if not prompt:
        await update.message.reply_text("Pakai format: /codex instruksi kamu")
        return

    await update.message.reply_text("Menjalankan Codex...")
    result = await asyncio.to_thread(run_codex_agent, prompt)
    await update.message.reply_text(f"Codex result:\n\n{format_output(result)}")


async def claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    prompt = " ".join(context.args).strip()
    if not prompt:
        await update.message.reply_text("Pakai format: /claude instruksi kamu")
        return

    await update.message.reply_text("Menjalankan Claude...")
    result = await asyncio.to_thread(run_claude_agent, prompt)
    await update.message.reply_text(f"Claude result:\n\n{format_output(result)}")


async def reset_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    context.user_data["chat_history"] = []
    await update.message.reply_text("Riwayat chat sudah direset.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    tg_user = update.effective_user
    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    active_project = project_store.get_active_project(chat_id, PROJECT_DIR)

    # Resolve user_id dari Telegram → DB. Kalau belum terdaftar, kasih /start dulu.
    user_id = _resolve_user_id_from_telegram(tg_user.id if tg_user else None)
    if user_id is None:
        await update.message.reply_text(
            "Akun belum terdaftar. Kirim /start dulu untuk auto-register."
        )
        return

    from app.composition import build_use_case
    from app.domain.messaging import ChatEventType, MessageContext

    use_case = build_use_case()
    ctx = MessageContext(
        user_id=user_id,
        conversation_id=str(chat_id),
        project_id=active_project.id,
        project_root=Path(active_project.root_path),
        project_name=active_project.name,
        telegram_user_id=tg_user.id if tg_user else None,
        extra={"telegram_username": f"@{tg_user.username}" if tg_user and tg_user.username else "-"},
    )

    text_chunks: list[str] = []
    final_sent = False

    try:
        for event in use_case.handle(user_text, ctx):
            if event.type == ChatEventType.APPROVAL_REQUIRED:
                summary = event.payload["summary"]
                plan_id = event.payload["plan_id"]
                await update.message.reply_text(
                    f"{summary}\n\n"
                    f"Konfirmasi: /approve {plan_id}\n"
                    f"Batalkan:   /reject {plan_id}\n"
                    f"(kedaluwarsa dalam 5 menit)"
                )
                final_sent = True
            elif event.type == ChatEventType.TEXT_CHUNK:
                text_chunks.append(event.payload["text"])
            elif event.type == ChatEventType.FINAL:
                final_text = event.payload.get("text") or "".join(text_chunks)
                if final_text.strip():
                    await update.message.reply_text(format_output(final_text))
                final_sent = True
            elif event.type == ChatEventType.ERROR:
                await update.message.reply_text(
                    f"Maaf, terjadi error: {event.payload['message']}"
                )
                final_sent = True
            elif event.type == ChatEventType.DELEGATE_TO_AGENT:
                # Delegasi ke worker user (Codex/Claude/GLM via WS).
                await _handle_agent_delegation(
                    update,
                    user_id=user_id,
                    agent=str(event.payload.get("agent", "codex")),
                    prompt=str(event.payload.get("prompt", "")),
                )
                final_sent = True
    except Exception as exc:  # defensive — use case sudah catch internal, ini safety net
        await update.message.reply_text(f"Internal error: {exc}")
        return

    # Kalau use case selesai tanpa FINAL (mis. early return), pastikan minimal ada respons
    if not final_sent and text_chunks:
        await update.message.reply_text(format_output("".join(text_chunks)))


async def _handle_agent_delegation(
    update: Update,
    *,
    user_id: str,
    agent: str,
    prompt: str,
) -> None:
    """Forward delegate event ke worker user, kumpulin chunks, kirim ke Telegram.

    Karena Telegram tidak ideal untuk streaming (rate limit edit), kita kumpulin
    semua chunks dulu lalu kirim 1-2 message akhir.
    """
    from app.adapters.audit import log_event
    from app.interfaces.worker_ws import (
        NoWorkerAvailableError,
        dispatch_agent_job,
    )

    if not prompt:
        await update.message.reply_text("Prompt agent kosong.")
        return

    await update.message.reply_text(f"⚙️  Delegasi ke `{agent}` di mesin kamu…")
    await log_event(
        "agent_dispatch",
        user_id=user_id,
        agent=agent,
        prompt=prompt,
        status="started",
    )

    chunks: list[str] = []
    try:
        async for ev in dispatch_agent_job(user_id, agent, prompt):
            kind = ev.get("type", "")
            if kind == "job_queued":
                await update.message.reply_text(
                    f"⏳ {ev.get('message', 'queued — menunggu slot worker')}"
                )
                continue
            if kind == "job_chunk":
                chunks.append(str(ev.get("text", "")))
            elif kind == "job_done":
                summary = str(ev.get("summary", ""))
                full_output = "".join(chunks).strip()
                if len(full_output) <= 4000:
                    msg = full_output or summary
                    await update.message.reply_text(format_output(msg))
                else:
                    await update.message.reply_text(
                        format_output(full_output[-3800:]) + "\n\n[output dipotong]"
                    )
                if summary:
                    await update.message.reply_text(f"✓ {agent}: {summary}")
                await log_event(
                    "agent_done",
                    user_id=user_id,
                    agent=agent,
                    status="ok",
                    detail=summary,
                )
                return
            elif kind == "job_error":
                err = str(ev.get("message", ""))
                await update.message.reply_text(f"❌ Agent {agent} error: {err}")
                await log_event(
                    "agent_error",
                    user_id=user_id,
                    agent=agent,
                    status="error",
                    detail=err,
                )
                return
    except NoWorkerAvailableError as exc:
        await update.message.reply_text(
            f"⚠️  Worker tidak tersedia: {exc}\n"
            "Buka TUI di komputer kamu supaya bisa delegasi ke agent."
        )
        await log_event(
            "agent_error",
            user_id=user_id,
            agent=agent,
            status="error",
            detail=str(exc),
        )


def _resolve_user_id_from_telegram(telegram_user_id: int | None) -> str | None:
    """Lookup user_id (UUID) berdasarkan telegram_user_id."""
    if telegram_user_id is None:
        return None
    from app.adapters.database.repositories import ControlPlaneRepository
    from app.adapters.database.session import session_scope

    try:
        with session_scope(_get_db_session_factory()) as session:
            repo = ControlPlaneRepository(session)
            tenant = repo.resolve_by_telegram_user_id(telegram_user_id)
            return tenant.user_id if tenant else None
    except Exception:
        return None


async def project_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    args = context.args or []

    if not args:
        project = project_store.get_active_project(chat_id, PROJECT_DIR)
        await update.message.reply_text(
            f"Project aktif: {project.name}\n"
            f"ID: {project.id}\n"
            f"Path: {project.root_path}\n"
            f"Deskripsi: {project.description or '-'}"
        )
        return

    name = args[0]
    found = project_store.get_project(name)
    if found is None:
        await update.message.reply_text(
            f"Project '{name}' tidak ditemukan.\nGunakan /projects untuk melihat daftar."
        )
        return

    project_store.set_active_project(chat_id, found.id)
    await update.message.reply_text(
        f"Switched ke project: {found.name}\nPath: {found.root_path}"
    )


async def projects_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    active_id = project_store.get_active_project_id(chat_id)
    all_projects = project_store.list_projects()

    if not all_projects:
        await update.message.reply_text("Belum ada project terdaftar.")
        return

    lines = ["Daftar project:"]
    for p in all_projects:
        marker = " *" if p.id == active_id else ""
        lines.append(f"- {p.name} ({p.id}){marker}  →  {p.root_path}")
    lines.append("\n* = aktif saat ini")
    await update.message.reply_text("\n".join(lines))


async def project_add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Format: /project_add <nama> <path>\nContoh: /project_add myapp /home/ali/myapp"
        )
        return

    name = args[0]
    root_path = args[1]
    description = " ".join(args[2:]) if len(args) > 2 else ""

    try:
        project = project_store.add_project(name, root_path, description)
        await update.message.reply_text(
            f"Project ditambahkan!\nNama: {project.name}\nID: {project.id}\nPath: {project.root_path}"
        )
    except ProjectAlreadyExistsError as exc:
        await update.message.reply_text(str(exc))


async def project_info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    project = project_store.get_active_project(chat_id, PROJECT_DIR)
    project_path = Path(project.root_path).expanduser().resolve()

    git_info = run_process(["git", "log", "--oneline", "-3"], cwd=project_path)
    git_status = run_process(["git", "status", "--short", "--branch"], cwd=project_path)

    await update.message.reply_text(
        format_output(
            f"Project: {project.name} ({project.id})\n"
            f"Path: {project_path}\n"
            f"Deskripsi: {project.description or '-'}\n"
            f"Dibuat: {project.created_at[:10] if project.created_at else '-'}\n\n"
            f"Git status:\n{git_status}\n\n"
            f"3 commit terakhir:\n{git_info}"
        )
    )


async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Format: /approve <plan_id>")
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    plan_id = args[0]

    pending = pending_plans.consume(plan_id, chat_id)
    if pending is None:
        await update.message.reply_text(
            f"Plan '{plan_id}' tidak ditemukan atau sudah kedaluwarsa."
        )
        return

    action_name = pending.plan.intent
    if action_name not in EXECUTABLE_ACTIONS:
        await update.message.reply_text(
            f"Action '{action_name}' disetujui tapi belum ada executor-nya."
        )
        return

    result = action_registry.execute(action_name, pending.action_context)

    try:
        summary = call_qwen(
            f"Ringkas output server ini dalam bahasa Indonesia yang singkat:\n{result}"
        )
    except Exception:
        summary = result

    await update.message.reply_text(
        f"Approved & executed: {action_name}\n\n{format_output(summary)}"
    )


async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Format: /reject <plan_id>")
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    plan_id = args[0]

    if pending_plans.cancel(plan_id, chat_id):
        await update.message.reply_text("Plan dibatalkan.")
    else:
        await update.message.reply_text(
            f"Plan '{plan_id}' tidak ditemukan atau sudah kedaluwarsa."
        )


async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    plans = pending_plans.list_for_chat(chat_id)

    if not plans:
        await update.message.reply_text("Tidak ada plan yang menunggu approval.")
        return

    lines = [f"Plan pending ({len(plans)}):"]
    for p in plans:
        sisa = int((p.expires_at - __import__("datetime").datetime.now()).total_seconds() / 60)
        lines.append(
            f"- {p.plan.plan_id[:8]}...  action: {p.plan.intent}"
            f"  (kedaluwarsa ~{sisa} menit)"
        )
        lines.append(f"  /approve {p.plan.plan_id}")
    await update.message.reply_text("\n".join(lines))


