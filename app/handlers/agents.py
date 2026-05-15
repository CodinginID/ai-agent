from __future__ import annotations

import shutil

from app.config import settings
from app.handlers.process_runners import run_agent_process

VALID_CODEX_SANDBOXES: frozenset[str] = frozenset({
    "read-only", "workspace-write", "danger-full-access",
})

_CODEX_SANDBOX_ALIASES: dict[str, str] = {
    "readonly": "read-only",
    "read_only": "read-only",
    "seatbelt": "read-only",
    "sandbox": "read-only",
    "workspace": "workspace-write",
    "full": "danger-full-access",
    "full-access": "danger-full-access",
    "danger": "danger-full-access",
}


def agent_binary_status(binary_name: str) -> str:
    binary_path = shutil.which(binary_name)
    return binary_path or "tidak ditemukan di PATH"


def normalized_codex_sandbox() -> str | None:
    sandbox = settings.codex_sandbox.strip().lower()
    sandbox = _CODEX_SANDBOX_ALIASES.get(sandbox, sandbox)
    if sandbox not in VALID_CODEX_SANDBOXES:
        return None
    return sandbox


def validate_agent_prompt(prompt: str) -> str | None:
    if not prompt.strip():
        return "Prompt kosong."
    if len(prompt) > settings.agent_max_prompt_chars:
        return f"Prompt terlalu panjang. Maksimal {settings.agent_max_prompt_chars} karakter."
    if not settings.admin_user_ids and not settings.allow_unrestricted_access:
        return "Isi ADMIN_USER_IDS di .env dulu sebelum mengaktifkan akses Codex/Claude dari Telegram."
    return None


def build_agent_prompt(user_prompt: str, agent_name: str) -> str:
    access_mode = (
        f"Codex sandbox={normalized_codex_sandbox() or settings.codex_sandbox}"
        if agent_name == "Codex"
        else (
            f"Claude permission={settings.claude_permission_mode}, "
            f"tools={settings.claude_tools or settings.claude_allowed_tools or 'default'}"
        )
    )
    return f"""
Kamu sedang dipanggil dari private Telegram bot untuk membantu user mengelola project/server.

Agent: {agent_name}
Working directory: {settings.agent_workdir}
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


def run_codex_agent(prompt: str) -> str:
    validation_error = validate_agent_prompt(prompt)
    if validation_error:
        return validation_error

    if not settings.enable_codex:
        return "Codex belum aktif. Set ENABLE_CODEX=true di .env lalu restart bot."

    codex_path = shutil.which(settings.codex_bin)
    if not codex_path:
        return f"Codex CLI tidak ditemukan: {settings.codex_bin}"

    sandbox = normalized_codex_sandbox()
    if not sandbox:
        allowed = ", ".join(sorted(VALID_CODEX_SANDBOXES))
        return f"CODEX_SANDBOX tidak valid: {settings.codex_sandbox}. Allowed: {allowed}"

    args = [
        codex_path,
        "exec",
        "--cd",
        str(settings.agent_workdir),
        "--sandbox",
        sandbox,
        "--ask-for-approval",
        "never",
        "--skip-git-repo-check",
        "--ephemeral",
        "--color",
        "never",
    ]
    if settings.codex_model:
        args.extend(["--model", settings.codex_model])

    args.append(build_agent_prompt(prompt, "Codex"))
    return run_agent_process(args)


def run_claude_agent(prompt: str) -> str:
    validation_error = validate_agent_prompt(prompt)
    if validation_error:
        return validation_error

    if not settings.enable_claude:
        return "Claude belum aktif. Set ENABLE_CLAUDE=true di .env lalu restart bot."

    claude_path = shutil.which(settings.claude_bin)
    if not claude_path:
        return f"Claude CLI tidak ditemukan: {settings.claude_bin}"

    args = [
        claude_path,
        "--print",
        "--no-session-persistence",
        "--permission-mode",
        settings.claude_permission_mode,
        "--output-format",
        "text",
    ]
    if settings.claude_tools:
        args.extend(["--tools", settings.claude_tools])
    if settings.claude_allowed_tools and settings.claude_allowed_tools.lower() != "default":
        args.extend(["--allowedTools", settings.claude_allowed_tools])
    if settings.claude_model:
        args.extend(["--model", settings.claude_model])

    args.append(build_agent_prompt(prompt, "Claude"))
    return run_agent_process(args)


# Re-export for backward compatibility — callers that do
# `from app.handlers.agents import agent_status_text` continue to work.
from app.handlers.agents_discovery import agent_status_text as agent_status_text  # noqa: E402
