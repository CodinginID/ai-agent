from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _normalize_database_url(url: str) -> str:
    """Pastikan SQLAlchemy pakai driver psycopg v3 untuk Postgres.

    Neon kasih connection string ``postgresql://...`` atau ``postgres://...``;
    SQLAlchemy butuh skema eksplisit kalau mau driver psycopg3.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    ollama_host: str
    qwen_url: str
    qwen_model: str
    project_dir: Path
    command_timeout: int
    max_reply_chars: int
    chat_history_limit: int
    allow_unrestricted_access: bool
    admin_user_ids: frozenset[int]
    allowed_manual_commands: frozenset[str]

    enable_codex: bool
    enable_claude: bool
    agent_timeout: int
    agent_workdir: Path
    agent_max_prompt_chars: int
    codex_bin: str
    codex_model: str
    codex_sandbox: str
    claude_bin: str
    claude_model: str
    claude_permission_mode: str
    claude_allowed_tools: str
    claude_tools: str
    enable_glm: bool
    glm_bin: str
    glm_model: str
    glm_access_mode: str
    agent_role_engineer: str
    agent_role_architect: str
    agent_role_reviewer: str

    enable_terminal_tools: bool
    terminal_timeout: int
    terminal_workdir: Path
    terminal_allowed_commands: frozenset[str]

    enable_webhook: bool
    webhook_url: str
    webhook_secret: str
    port: int
    database_url: str
    database_migration_url: str

    app_url: str
    google_client_id: str
    google_client_secret: str
    admin_token: str


_DEFAULT_MANUAL_COMMANDS: frozenset[str] = frozenset({
    "docker", "git", "ls", "ps", "df", "du", "free",
    "uptime", "whoami", "pwd", "hostname",
})

_DEFAULT_TERMINAL_COMMANDS: frozenset[str] = frozenset({
    "btop", "spf", "fastfetch", "neofetch", "df", "free", "uptime",
    "whoami", "pwd", "ls", "git", "docker", "systemctl", "journalctl", "tail",
})


def load_settings() -> Settings:
    _load_env_file(BASE_DIR / ".env")

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    project_dir = Path(os.getenv("PROJECT_DIR", str(BASE_DIR))).expanduser().resolve()
    agent_workdir = Path(os.getenv("AGENT_WORKDIR", str(project_dir))).expanduser().resolve()
    terminal_workdir = Path(os.getenv("TERMINAL_WORKDIR", str(project_dir))).expanduser().resolve()
    default_database_url = f"sqlite:///{BASE_DIR / 'data' / 'control_plane.sqlite3'}"
    database_url = _normalize_database_url(os.getenv("DATABASE_URL", default_database_url))

    admin_user_ids: frozenset[int] = frozenset(
        int(uid.strip())
        for uid in os.getenv("ADMIN_USER_IDS", "").replace(";", ",").split(",")
        if uid.strip().isdigit()
    )

    raw_terminal = os.getenv("TERMINAL_ALLOWED_COMMANDS", "").strip()
    terminal_cmds: frozenset[str] = (
        frozenset(c.strip() for c in raw_terminal.split(",") if c.strip())
        if raw_terminal
        else _DEFAULT_TERMINAL_COMMANDS
    )

    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        ollama_host=ollama_host,
        qwen_url=os.getenv("QWEN_URL", f"{ollama_host}/api/generate"),
        qwen_model=os.getenv("QWEN_MODEL", os.getenv("OLLAMA_MODEL", "qwen2.5:3b")),
        project_dir=project_dir,
        command_timeout=int(os.getenv("COMMAND_TIMEOUT", "20")),
        max_reply_chars=3800,
        chat_history_limit=int(os.getenv("CHAT_HISTORY_LIMIT", "6")),
        allow_unrestricted_access=_env_bool("ALLOW_UNRESTRICTED_ACCESS"),
        admin_user_ids=admin_user_ids,
        allowed_manual_commands=_DEFAULT_MANUAL_COMMANDS,
        enable_codex=_env_bool("ENABLE_CODEX"),
        enable_claude=_env_bool("ENABLE_CLAUDE"),
        agent_timeout=int(os.getenv("AGENT_TIMEOUT", "180")),
        agent_workdir=agent_workdir,
        agent_max_prompt_chars=int(os.getenv("AGENT_MAX_PROMPT_CHARS", "6000")),
        codex_bin=os.getenv("CODEX_BIN", "codex"),
        codex_model=os.getenv("CODEX_MODEL", ""),
        codex_sandbox=os.getenv("CODEX_SANDBOX", "read-only"),
        claude_bin=os.getenv("CLAUDE_BIN", "claude"),
        claude_model=os.getenv("CLAUDE_MODEL", ""),
        claude_permission_mode=os.getenv("CLAUDE_PERMISSION_MODE", "dontAsk"),
        claude_allowed_tools=os.getenv("CLAUDE_ALLOWED_TOOLS", "Read,Grep,Glob"),
        claude_tools=os.getenv("CLAUDE_TOOLS", ""),
        enable_glm=_env_bool("ENABLE_GLM"),
        glm_bin=os.getenv("GLM_BIN", "glm"),
        glm_model=os.getenv("GLM_MODEL", ""),
        glm_access_mode=os.getenv("GLM_ACCESS_MODE", "read-only"),
        agent_role_engineer=os.getenv("AGENT_ROLE_ENGINEER", "codex").strip().lower(),
        agent_role_architect=os.getenv("AGENT_ROLE_ARCHITECT", "glm").strip().lower(),
        agent_role_reviewer=os.getenv("AGENT_ROLE_REVIEWER", "claude").strip().lower(),
        enable_terminal_tools=_env_bool("ENABLE_TERMINAL_TOOLS"),
        terminal_timeout=int(os.getenv("TERMINAL_TIMEOUT", "20")),
        terminal_workdir=terminal_workdir,
        terminal_allowed_commands=terminal_cmds,
        enable_webhook=_env_bool("ENABLE_WEBHOOK"),
        webhook_url=os.getenv("WEBHOOK_URL", "").rstrip("/"),
        webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
        port=int(os.getenv("PORT", "8080")),
        database_url=database_url,
        database_migration_url=os.getenv("DATABASE_MIGRATION_URL", database_url),
        app_url=os.getenv("APP_URL", "http://localhost:8080").rstrip("/"),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        admin_token=os.getenv("ADMIN_TOKEN", "").strip(),
    )


settings = load_settings()
