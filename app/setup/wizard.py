from __future__ import annotations

import http.server
import os
import socket
import sys
import threading
import urllib.parse
import webbrowser
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

_AUTH_SUCCESS_HTML = b"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>AI Agent</title>
  <style>
    *    { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f172a;
           color: #e2e8f0; display: flex; align-items: center;
           justify-content: center; min-height: 100vh; }
    .card { text-align: center; padding: 48px 40px; max-width: 400px; }
    .icon { font-size: 3rem; margin-bottom: 16px; }
    h1   { color: #4ade80; font-size: 1.6rem; margin-bottom: 10px; }
    p    { color: #94a3b8; font-size: 0.95rem; line-height: 1.6; }
    .dim { margin-top: 28px; font-size: 0.8rem; color: #475569; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#10003;</div>
    <h1>Login Berhasil</h1>
    <p>Akun kamu sudah terverifikasi.<br>Kembali ke terminal untuk melanjutkan.</p>
    <p class="dim">Halaman ini bisa ditutup.</p>
  </div>
</body>
</html>"""


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
    print(f"  → {url}\n")


def _prompt(label: str, secret: bool = False) -> str:
    try:
        if secret:
            import getpass
            return getpass.getpass(f"  {label}: ").strip()
        return input(f"  {label}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nSetup dibatalkan.")
        sys.exit(0)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return int(s.getsockname()[1])


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


# ── Step 1: Google Auth ───────────────────────────────────────────────────────

def _step_google_auth(lines: list[str]) -> tuple[str, str, list[str]]:
    """
    Returns (email, display_name, env_lines_unchanged).
    Jika GOOGLE_CLIENT_ID/SECRET belum diisi, step ini dilewati (opsional).
    """
    print("Step 1/3 — Login dengan Google")
    print("─" * 43)

    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        print()
        print("  [SKIP] GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET belum diisi di .env.")
        print("  Untuk mengaktifkan Google login, isi dulu di .env:")
        print("    GOOGLE_CLIENT_ID=...")
        print("    GOOGLE_CLIENT_SECRET=...")
        print()
        print("  Dapatkan dari: console.cloud.google.com → Credentials → OAuth 2.0 Client ID")
        print()
        print("  Melanjutkan setup tanpa Google login...")
        return "", "", lines

    # Wizard pakai port yang sama dengan APP_URL agar redirect URI konsisten
    # dengan yang didaftarkan di Google Cloud Console
    app_url = os.getenv("APP_URL", "http://localhost:8080").rstrip("/")
    port_str = app_url.split(":")[-1] if ":" in app_url.split("//")[-1] else "8080"
    try:
        port = int(port_str)
    except ValueError:
        port = 8080

    redirect_uri = f"{app_url}/auth/google/callback"

    # Build Google OAuth URL sama persis seperti endpoint /auth/google/login
    import secrets
    import urllib.parse as _urlparse

    state = secrets.token_urlsafe(16)
    params = _urlparse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(_GOOGLE_SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"

    # Show QR + URL: user scans dari HP atau browser terbuka otomatis
    _show_qr(auth_url, "Scan atau klik untuk login dengan Google:")
    print(f"  Callback akan diterima di: {redirect_uri}")
    print("  Menunggu login di browser... (Ctrl+C untuk batalkan)")

    # Jalankan callback server sementara di port yang sama
    auth_code: list[str] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            params_qs = urllib.parse.parse_qs(parsed.query)
            code = params_qs.get("code", [None])[0]
            if code:
                auth_code.append(code)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_AUTH_SUCCESS_HTML)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("localhost", port), _Handler)
    threading.Timer(0.5, lambda: webbrowser.open(auth_url)).start()

    try:
        server.handle_request()
    except KeyboardInterrupt:
        print("\n\nSetup dibatalkan.")
        sys.exit(0)

    if not auth_code:
        print("\n  Login gagal — tidak ada kode yang diterima.")
        sys.exit(1)

    # Exchange code → access token
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": auth_code[0],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    token_data: dict[str, object] = token_resp.json()
    access_token = str(token_data.get("access_token", ""))

    if not access_token:
        print("\n  Gagal mendapatkan access token.")
        sys.exit(1)

    info_resp = requests.get(
        "https://www.googleapis.com/oauth2/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    info: dict[str, object] = info_resp.json()
    email = str(info.get("email", ""))
    name = str(info.get("name", ""))

    print(f"\n  ✓  Login sebagai: {name} <{email}>")
    return email, name, lines


# ── Step 2: Telegram bot setup ────────────────────────────────────────────────

def _validate_telegram_token(token: str) -> str | None:
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
    _show_qr("https://t.me/BotFather", "Buat bot baru — scan atau buka @BotFather:")
    print("  Di @BotFather: ketik /newbot → ikuti instruksi → copy token")
    print()

    token = ""
    bot_username = ""
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


# ── Step 3: Ollama ────────────────────────────────────────────────────────────

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

    # Step 1 — Google login (user cukup klik, tidak perlu setup apapun)
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

    # Done — show QR to bot
    print()
    print("─" * 43)
    if email:
        print(f"  Setup selesai! Login sebagai {email}")
    else:
        print("  Setup selesai!")
    _show_qr(
        f"https://t.me/{bot_username}",
        f"Scan untuk buka @{bot_username} di Telegram:",
    )
    print("  Kirim /start ke bot untuk mendaftarkan akun kamu.")
    print()
    print("  Jalankan ulang untuk mulai bot:")
    print("    make dev")
    print("─" * 43)
    print()

    sys.exit(0)
