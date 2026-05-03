from __future__ import annotations

import os
import sys
from pathlib import Path

import requests  # type: ignore[import-untyped]

_PLACEHOLDER_TOKENS: frozenset[str] = frozenset({
    "", "ISI_TOKEN_KAMU_DI_SINI", "ISI_TOKEN_TELEGRAM_KAMU_DI_SINI",
})

_GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def needs_setup(token: str) -> bool:
    return not token or token.strip() in _PLACEHOLDER_TOKENS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_header() -> None:
    print()
    print("┌─────────────────────────────────────────┐")
    print("│   AI Agent — Setup Pertama Kali          │")
    print("└─────────────────────────────────────────┘")
    print()


def _show_qr(url: str, label: str) -> None:
    """Print QR code to terminal. Gracefully skips if qrcode is not installed."""
    print(f"\n  {label}")
    try:
        import qrcode  # type: ignore[import-untyped]
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception:
        pass
    print(f"  → {url}")


def _prompt(label: str, secret: bool = False) -> str:
    try:
        if secret:
            import getpass
            return getpass.getpass(f"  {label}: ").strip()
        return input(f"  {label}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nSetup dibatalkan.")
        sys.exit(0)


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


def _save_env(env_path: Path, lines: list[str]) -> None:
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Step 1: Google Auth ────────────────────────────────────────────────────────

def _step_google_auth(lines: list[str]) -> tuple[str, str, list[str]]:
    """
    Returns (email, display_name, updated_env_lines).
    Saves GOOGLE_CLIENT_ID / SECRET to env if entered for the first time.
    """
    print("Step 1/3 — Login Google")
    print("─" * 43)

    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        print()
        print("  Google OAuth credentials belum dikonfigurasi.")
        print("  Cara mendapatkannya (satu kali saja):")
        print()
        print("    1. Buka https://console.cloud.google.com/apis/credentials")
        print("    2. Create Credentials → OAuth 2.0 Client ID")
        print("    3. Application type: Desktop App")
        print("    4. Copy Client ID dan Client Secret")
        print()

        while not client_id:
            client_id = _prompt("Google Client ID")
        while not client_secret:
            client_secret = _prompt("Google Client Secret", secret=True)

        lines = _set_env_key(lines, "GOOGLE_CLIENT_ID", client_id)
        lines = _set_env_key(lines, "GOOGLE_CLIENT_SECRET", client_secret)

    print()
    print("  Membuka browser untuk login Google...")
    print("  (Jika browser tidak terbuka, salin URL yang muncul)\n")

    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=_GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", open_browser=True)

    resp = requests.get(
        "https://www.googleapis.com/oauth2/v1/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=10,
    )
    info: dict[str, object] = resp.json()
    email = str(info.get("email", ""))
    name = str(info.get("name", ""))

    print(f"\n  ✓  Login sebagai: {name} <{email}>")
    return email, name, lines


# ── Step 2: Telegram bot setup ─────────────────────────────────────────────────

def _validate_telegram_token(token: str) -> str | None:
    """Returns bot @username if valid, None otherwise."""
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        data: dict[str, object] = resp.json()
        if data.get("ok"):
            result = data["result"]
            if isinstance(result, dict):
                return str(result["username"])
    except Exception:
        pass
    return None


def _step_bot_setup() -> tuple[str, str]:
    """Returns (token, bot_username)."""
    print()
    print("Step 2/3 — Setup Bot Telegram")
    print("─" * 43)

    _show_qr("https://t.me/BotFather", "Buat bot baru — scan atau buka link ini:")
    print()
    print("  Di @BotFather: kirim /newbot → ikuti instruksi → copy token")
    print()

    bot_username = ""
    token = ""
    while True:
        token = _prompt("Token bot (dari @BotFather)")
        if not token:
            print("  Token tidak boleh kosong.\n")
            continue

        print("  Memvalidasi... ", end="", flush=True)
        result = _validate_telegram_token(token)
        if result:
            bot_username = result
            print(f"✓  @{bot_username}")
            break
        print("✗  Token tidak valid. Coba lagi.\n")

    return token, bot_username


# ── Step 3: Ollama + selesai ───────────────────────────────────────────────────

def _step_ollama() -> str:
    print()
    print("Step 3/3 — Konfigurasi Ollama")
    print("─" * 43)
    print()
    raw = _prompt("Ollama host [http://localhost:11434]")
    return raw or "http://localhost:11434"


# ── Migration ─────────────────────────────────────────────────────────────────

def _run_migration(project_root: Path) -> None:
    from alembic import command as alembic_cmd
    from alembic.config import Config

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    alembic_cmd.upgrade(cfg, "head")


# ── Main wizard ───────────────────────────────────────────────────────────────

def run_setup_wizard(env_path: Path) -> None:
    _print_header()

    lines = _read_env_lines(env_path)

    # Step 1 — Google Auth
    email, _display_name, lines = _step_google_auth(lines)

    # Step 2 — Telegram bot token
    token, bot_username = _step_bot_setup()
    lines = _set_env_key(lines, "TELEGRAM_BOT_TOKEN", token)

    # Step 3 — Ollama
    ollama_host = _step_ollama()
    lines = _set_env_key(lines, "OLLAMA_HOST", ollama_host)
    lines = _set_env_key(lines, "OLLAMA_MODEL", "qwen2.5:3b")

    # Save .env
    print()
    print("  Menyimpan konfigurasi... ", end="", flush=True)
    _save_env(env_path, lines)
    print("✓")

    # Migration
    print("  Membuat database...     ", end="", flush=True)
    try:
        _run_migration(env_path.parent)
        print("✓")
    except Exception as exc:
        print(f"✗  {exc}")
        sys.exit(1)

    # Done — show bot QR
    print()
    print("─" * 43)
    print(f"  Setup selesai! Login sebagai {email}")
    _show_qr(
        f"https://t.me/{bot_username}",
        f"Scan untuk buka @{bot_username} di Telegram:",
    )
    print()
    print("  Kirim /start ke bot untuk mendaftarkan akun.")
    print("─" * 43)
    print()

    # Restart process so fresh .env is loaded
    os.execv(sys.executable, [sys.executable, *sys.argv])
