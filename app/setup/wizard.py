from __future__ import annotations

import os
import sys
from pathlib import Path

import requests  # type: ignore[import-untyped]

_PLACEHOLDER_TOKENS: frozenset[str] = frozenset({
    "", "ISI_TOKEN_KAMU_DI_SINI", "ISI_TOKEN_TELEGRAM_KAMU_DI_SINI",
})


def needs_setup(token: str) -> bool:
    return not token or token.strip() in _PLACEHOLDER_TOKENS


def _validate_token(token: str) -> str | None:
    """Returns bot @username if token valid, None otherwise."""
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=8,
        )
        data: dict[str, object] = resp.json()
        if data.get("ok"):
            result = data["result"]
            if isinstance(result, dict):
                return str(result["username"])
    except Exception:
        pass
    return None


def _read_env_lines(env_path: Path) -> list[str]:
    if env_path.exists():
        return env_path.read_text(encoding="utf-8").splitlines()
    example = env_path.parent / ".env.example"
    if example.exists():
        return example.read_text(encoding="utf-8").splitlines()
    return []


def _set_env_key(lines: list[str], key: str, value: str) -> list[str]:
    updated = False
    result: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            result.append(f"{key}={value}")
            updated = True
        else:
            result.append(line)
    if not updated:
        result.append(f"{key}={value}")
    return result


def _run_migration(project_root: Path) -> None:
    from alembic import command as alembic_cmd
    from alembic.config import Config

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    alembic_cmd.upgrade(cfg, "head")


def run_setup_wizard(env_path: Path) -> None:
    print()
    print("┌─────────────────────────────────────────┐")
    print("│   AI Agent — Setup Pertama Kali          │")
    print("└─────────────────────────────────────────┘")
    print()
    print("Token bot Telegram belum dikonfigurasi.")
    print()
    print("Dapatkan token dari @BotFather:")
    print("  1. Buka Telegram → cari @BotFather")
    print("  2. Kirim /newbot dan ikuti instruksi")
    print("  3. Copy token yang diberikan")
    print()

    # Step 1: Token
    bot_username: str | None = None
    token: str = ""
    while True:
        try:
            token = input("Token bot: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSetup dibatalkan.")
            sys.exit(0)

        if not token:
            print("Token tidak boleh kosong. Coba lagi.\n")
            continue

        print("Memvalidasi... ", end="", flush=True)
        bot_username = _validate_token(token)
        if bot_username:
            print(f"✓  @{bot_username}")
            break
        print("✗  Token tidak valid. Coba lagi.\n")

    # Step 2: Ollama host
    print()
    try:
        raw = input("Ollama host [http://localhost:11434]: ").strip()
    except (KeyboardInterrupt, EOFError):
        raw = ""
    ollama_host = raw or "http://localhost:11434"

    # Step 3: Save .env
    print()
    print("Menyimpan konfigurasi... ", end="", flush=True)
    lines = _read_env_lines(env_path)
    lines = _set_env_key(lines, "TELEGRAM_BOT_TOKEN", token)
    lines = _set_env_key(lines, "OLLAMA_HOST", ollama_host)
    lines = _set_env_key(lines, "OLLAMA_MODEL", "qwen2.5:3b")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("✓")

    # Step 4: Migration
    print("Membuat database...     ", end="", flush=True)
    try:
        _run_migration(env_path.parent)
        print("✓")
    except Exception as exc:
        print(f"✗  {exc}")
        sys.exit(1)

    # Done
    print()
    print("─" * 43)
    print(f"Setup selesai! Bot kamu: https://t.me/{bot_username}")
    print()
    print("Buka link itu di Telegram, lalu kirim /start")
    print("untuk mendaftarkan akun kamu.")
    print("─" * 43)
    print()

    # Restart process so new .env is loaded
    os.execv(sys.executable, [sys.executable, *sys.argv])
