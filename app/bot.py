import asyncio
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
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters


BASE_DIR = Path(__file__).resolve().parent.parent
PLACEHOLDER_TOKENS = {"", "ISI_TOKEN_KAMU_DI_SINI", "ISI_TOKEN_TELEGRAM_KAMU_DI_SINI"}


def load_env_file(path: str | Path = ".env"):
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
QWEN_URL = os.getenv("QWEN_URL", f"{OLLAMA_HOST}/api/generate")
QWEN_MODEL = os.getenv("QWEN_MODEL", os.getenv("OLLAMA_MODEL", "qwen"))
PROJECT_DIR = Path(os.getenv("PROJECT_DIR", str(BASE_DIR))).expanduser().resolve()
COMMAND_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", "20"))
MAX_REPLY_CHARS = 3800
CHAT_HISTORY_LIMIT = int(os.getenv("CHAT_HISTORY_LIMIT", "6"))
ALLOW_UNRESTRICTED_ACCESS = env_bool("ALLOW_UNRESTRICTED_ACCESS")

ENABLE_CODEX = env_bool("ENABLE_CODEX")
ENABLE_CLAUDE = env_bool("ENABLE_CLAUDE")
AGENT_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "180"))
AGENT_WORKDIR = Path(os.getenv("AGENT_WORKDIR", str(PROJECT_DIR))).expanduser().resolve()
AGENT_MAX_PROMPT_CHARS = int(os.getenv("AGENT_MAX_PROMPT_CHARS", "6000"))
CODEX_BIN = os.getenv("CODEX_BIN", "codex")
CODEX_MODEL = os.getenv("CODEX_MODEL", "")
CODEX_SANDBOX = os.getenv("CODEX_SANDBOX", "read-only")
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "")
CLAUDE_PERMISSION_MODE = os.getenv("CLAUDE_PERMISSION_MODE", "dontAsk")
CLAUDE_ALLOWED_TOOLS = os.getenv("CLAUDE_ALLOWED_TOOLS", "Read,Grep,Glob")

VALID_CODEX_SANDBOXES = {"read-only", "workspace-write", "danger-full-access"}
CODEX_SANDBOX_ALIASES = {
    "readonly": "read-only",
    "read_only": "read-only",
    "seatbelt": "read-only",
    "sandbox": "read-only",
    "workspace": "workspace-write",
}

ADMIN_USER_IDS = {
    int(user_id.strip())
    for user_id in os.getenv("ADMIN_USER_IDS", "").replace(";", ",").split(",")
    if user_id.strip().isdigit()
}

ALLOWED_MANUAL_COMMANDS = {
    "docker",
    "git",
    "ls",
    "ps",
    "df",
    "du",
    "free",
    "uptime",
    "whoami",
    "pwd",
    "hostname",
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
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd or PROJECT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=COMMAND_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return f"Command tidak ditemukan: {args[0]}"
    except subprocess.TimeoutExpired:
        return f"Command timeout setelah {COMMAND_TIMEOUT} detik."
    except Exception as exc:
        return f"Gagal menjalankan command: {exc}"

    output = result.stdout.strip()
    if result.returncode != 0:
        output = f"Exit code: {result.returncode}\n{output}"

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


def validate_agent_prompt(prompt: str) -> str | None:
    if not prompt.strip():
        return "Prompt kosong."

    if len(prompt) > AGENT_MAX_PROMPT_CHARS:
        return f"Prompt terlalu panjang. Maksimal {AGENT_MAX_PROMPT_CHARS} karakter."

    if not ADMIN_USER_IDS and not ALLOW_UNRESTRICTED_ACCESS:
        return "Isi ADMIN_USER_IDS di .env dulu sebelum mengaktifkan akses Codex/Claude dari Telegram."

    return None


def build_agent_prompt(user_prompt: str, agent_name: str) -> str:
    return f"""
Kamu sedang dipanggil dari private Telegram bot untuk membantu user mengelola project/server.

Agent: {agent_name}
Working directory: {AGENT_WORKDIR}

Aturan respons:
- Jawab dalam bahasa user.
- Buat output ringkas dan cocok untuk Telegram.
- Jika environment read-only atau tool tidak punya izin edit, jelaskan batasannya.
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
    if CLAUDE_ALLOWED_TOOLS:
        args.extend(["--allowedTools", CLAUDE_ALLOWED_TOOLS])
    if CLAUDE_MODEL:
        args.extend(["--model", CLAUDE_MODEL])

    args.append(build_agent_prompt(prompt, "Claude"))
    return run_agent_process(args)


def agent_status_text() -> str:
    return "\n".join(
        [
            "Agent CLI status",
            f"Admin restriction: {'nonaktif' if ALLOW_UNRESTRICTED_ACCESS else 'aktif'}",
            f"Agent workdir: {AGENT_WORKDIR}",
            f"Agent timeout: {AGENT_TIMEOUT}s",
            "",
            f"Codex enabled: {ENABLE_CODEX}",
            f"Codex binary: {agent_binary_status(CODEX_BIN)}",
            f"Codex sandbox: {CODEX_SANDBOX} -> {normalized_codex_sandbox() or 'invalid'}",
            f"Codex model: {CODEX_MODEL or '(default config)'}",
            "",
            f"Claude enabled: {ENABLE_CLAUDE}",
            f"Claude binary: {agent_binary_status(CLAUDE_BIN)}",
            f"Claude permission: {CLAUDE_PERMISSION_MODE}",
            f"Claude tools: {CLAUDE_ALLOWED_TOOLS or '(default)'}",
            f"Claude model: {CLAUDE_MODEL or '(default config)'}",
        ]
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
    for partition in partitions:
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except PermissionError:
            continue

        lines.append(
            f"{partition.mountpoint}: {usage.percent:.1f}% "
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


def action_git_status(_: dict | None = None) -> str:
    return run_process(["git", "status", "--short", "--branch"])


def action_list_files(_: dict | None = None) -> str:
    return run_process(["ls", "-lah"])


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

    lines.extend(
        [
            f"Bot user: {run_process(['whoami'])}",
            f"Working dir: {PROJECT_DIR}",
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


def is_greeting(text: str) -> bool:
    greetings = {
        "hi",
        "hai",
        "halo",
        "hello",
        "hey",
        "pagi",
        "siang",
        "sore",
        "malam",
        "assalamualaikum",
        "assalamu'alaikum",
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_unauthorized(update):
        return

    await update.message.reply_text(
        "Bot siap.\n\n"
        "Chat biasa:\n"
        "- hi\n"
        "- jelaskan docker itu apa\n"
        "- bantu analisa error ini\n"
        "- /ask apa beda docker image dan container\n\n"
        "Agent CLI:\n"
        "- /agents\n"
        "- /codex review singkat project ini\n"
        "- /claude jelaskan struktur project ini\n\n"
        "Contoh perintah:\n"
        "- cek status server\n"
        "- cek ram\n"
        "- cek disk\n"
        "- docker yang jalan apa aja\n"
        "- git status\n\n"
        "Manual command:\n"
        "/cmd docker ps\n"
        "/cmd git status\n"
        "/cmd df -h\n\n"
        "Cek Telegram user ID:\n"
        "/whoami\n\n"
        "Reset riwayat chat:\n"
        "/reset"
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
    if await deny_if_unauthorized(update):
        return

    await update.message.reply_text(format_output(agent_status_text()))


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
    try:
        intent = parse_intent_with_ai(user_text)
    except requests.RequestException as exc:
        await update.message.reply_text(f"Gagal menghubungi Qwen/Ollama: {exc}")
        return
    except Exception as exc:
        await update.message.reply_text(f"Gagal membaca intent: {exc}")
        return

    action = intent["action"]
    if action in {"chat", "unknown"}:
        await reply_chat(update, context, user_text)
        return

    user = update.effective_user
    intent["telegram_user"] = {
        "id": user.id if user else "-",
        "username": f"@{user.username}" if user and user.username else "-",
    }

    result = ACTIONS[action](intent)
    if action == "whoami":
        await update.message.reply_text(format_output(result))
        return

    try:
        summary = call_qwen(f"Ringkas output server ini dalam bahasa Indonesia yang singkat:\n{result}")
    except Exception:
        summary = result

    await update.message.reply_text(f"Action: {action}\n\n{format_output(summary)}")


def main():
    if TOKEN in PLACEHOLDER_TOKENS:
        raise RuntimeError("TELEGRAM_BOT_TOKEN belum diisi. Buat .env dari .env.example lalu isi token bot.")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("cmd", cmd))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("agents", agents))
    app.add_handler(CommandHandler("codex", codex))
    app.add_handler(CommandHandler("claude", claude))
    app.add_handler(CommandHandler("reset", reset_chat))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()


if __name__ == "__main__":
    main()
