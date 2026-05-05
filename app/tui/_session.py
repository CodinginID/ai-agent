"""Client-side session management untuk TUI.

Simpan session token di ``~/.config/ai-agent/session.json`` dengan permission
0600. Tidak punya akses DB — semua via HTTP ke backend.

File I/O lokal (load/save/clear/qr) tetap sync — fast & tidak boleh
yield ke loop di tengah-tengah. HTTP call ke backend async.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
import qrcode

from app.config import settings

_CONFIG_DIR = Path.home() / ".config" / "ai-agent"
_SESSION_FILE = _CONFIG_DIR / "session.json"


@dataclass
class Session:
    token: str
    user_id: str
    email: str
    display_name: str | None
    backend_url: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "token": self.token,
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
            "backend_url": self.backend_url,
        }


def load_session() -> Session | None:
    """Load session dari disk. Return None kalau tidak ada/corrupt/beda backend."""
    try:
        with _SESSION_FILE.open() as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if data.get("backend_url") != settings.app_url:
        return None
    if not data.get("token"):
        return None
    return Session(
        token=str(data["token"]),
        user_id=str(data.get("user_id", "")),
        email=str(data.get("email", "")),
        display_name=data.get("display_name"),
        backend_url=str(data["backend_url"]),
    )


def save_session(session: Session) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _SESSION_FILE.write_text(json.dumps(session.to_dict(), indent=2))
    try:
        os.chmod(_SESSION_FILE, 0o600)
    except OSError:
        # Windows atau filesystem tanpa POSIX perms — abaikan.
        pass


def clear_session() -> None:
    try:
        _SESSION_FILE.unlink()
    except FileNotFoundError:
        pass


# ── HTTP API ke backend ──────────────────────────────────────────────────────

class LoginAborted(Exception):
    """User cancel atau code expired."""


async def validate_session(token: str) -> tuple[Session | None, str | None]:
    """GET /auth/me untuk verifikasi token masih hidup.

    Return ``(session, None)`` kalau valid, atau ``(None, reason)`` dengan
    alasan teknis kenapa gagal — supaya TUI bisa tampilin langsung tanpa
    butuh debug env var.
    """
    try:
        # 15 detik kasih ruang untuk cold-start backend (Neon SSL handshake
        # bisa 5-6 detik di request pertama setelah container restart).
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as c:
            r = await c.get(
                f"{settings.app_url}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        return None, f"http error: {type(exc).__name__}: {exc}"

    if r.status_code != 200:
        body = r.text[:160].strip()
        return None, f"HTTP {r.status_code} — {body or '(empty body)'}"

    try:
        data = r.json()
    except Exception as exc:
        return None, f"JSON decode: {exc} (body={r.text[:160]!r})"

    try:
        return (
            Session(
                token=token,
                user_id=str(data.get("user_id", "")),
                email=str(data.get("email", "")),
                display_name=data.get("display_name"),
                backend_url=settings.app_url,
            ),
            None,
        )
    except Exception as exc:
        return None, f"Session construction: {exc} (data={data!r})"


async def request_pair_code() -> tuple[str, str]:
    """POST /auth/tui/start. Return (code, login_url)."""
    async with httpx.AsyncClient(timeout=5.0, trust_env=False) as c:
        r = await c.post(f"{settings.app_url}/auth/tui/start")
    r.raise_for_status()
    data = r.json()
    return str(data["code"]), str(data["login_url"])


async def poll_pair_code(code: str) -> str | None:
    """POST /auth/tui/poll. Return session_token kalau sudah paired, else None.

    Raise ``LoginAborted`` kalau backend bilang code expired/unknown.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as c:
            r = await c.post(
                f"{settings.app_url}/auth/tui/poll",
                json={"code": code},
            )
    except httpx.HTTPError:
        return None
    if r.status_code == 410:
        raise LoginAborted("kode pair expired atau tidak dikenal")
    if r.status_code == 200:
        try:
            data = r.json()
        except Exception as exc:
            raise LoginAborted(
                f"backend balas 200 tapi body bukan JSON valid: {exc} "
                f"(body={r.text[:120]!r})"
            ) from exc
        token = data.get("session_token")
        if data.get("status") == "paired" and token:
            return str(token)
        # 200 tapi bukan paired/token kosong — bug yang tidak boleh terjadi.
        raise LoginAborted(f"backend balas 200 tapi payload aneh: {data!r}")
    # 202 pending atau status lain → terus loop polling.
    return None


async def revoke_session(token: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as c:
            r = await c.post(
                f"{settings.app_url}/auth/tui/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


# ── QR rendering ─────────────────────────────────────────────────────────────

def qr_ascii(text: str) -> str:
    """Render QR ke string ASCII pakai blok unicode setengah — kompak di terminal."""
    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()  # list[list[bool]]

    # Pakai ▀ (upper half block) — tiap baris terminal merepresentasikan
    # 2 baris QR, jadi tinggi-nya separuh.
    lines: list[str] = []
    for y in range(0, len(matrix), 2):
        row = ""
        for x in range(len(matrix[y])):
            top = matrix[y][x]
            bot = matrix[y + 1][x] if y + 1 < len(matrix) else False
            if top and bot:
                row += "█"  # full block
            elif top and not bot:
                row += "▀"  # upper half
            elif not top and bot:
                row += "▄"  # lower half
            else:
                row += " "
        lines.append(row)
    return "\n".join(lines)
