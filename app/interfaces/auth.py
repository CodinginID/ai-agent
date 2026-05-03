from __future__ import annotations

import secrets
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"
_SCOPES = "openid email profile"
_STATE_TTL = timedelta(minutes=10)

# In-memory CSRF state store — fine for single-process dev; use Redis in production
_pending_states: dict[str, datetime] = {}


def _redirect_uri() -> str:
    return f"{settings.app_url}/auth/google/callback"


def _purge_expired_states() -> None:
    now = datetime.now(UTC)
    expired = [k for k, v in _pending_states.items() if now - v > _STATE_TTL]
    for k in expired:
        del _pending_states[k]


# ── HTML pages ────────────────────────────────────────────────────────────────

_PAGE_STYLE = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { text-align: center; padding: 48px 40px; max-width: 440px; width: 100%; }
  .icon { font-size: 3rem; margin-bottom: 16px; }
  h1   { font-size: 1.6rem; margin-bottom: 10px; }
  p    { color: #94a3b8; font-size: 0.95rem; line-height: 1.6; }
  .meta { margin-top: 8px; font-size: 0.85rem; color: #64748b; }
  .dim  { margin-top: 28px; font-size: 0.8rem; color: #475569; }
  a    { color: #60a5fa; text-decoration: none; }
  .btn { display: inline-block; margin-top: 24px; padding: 12px 28px;
         background: #4285F4; color: #fff; border-radius: 6px;
         font-size: 0.95rem; font-weight: 500; text-decoration: none; }
  .btn:hover { background: #3367D6; }
  .err { color: #f87171; }
</style>
"""


def _page(body: str) -> str:
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>AI Agent</title>{_PAGE_STYLE}</head><body>{body}</body></html>"


def _success_page(name: str, email: str, is_new: bool) -> str:
    greeting = "Akun berhasil dibuat" if is_new else "Selamat datang kembali"
    return _page(f"""
<div class="card">
  <div class="icon">&#10003;</div>
  <h1 style="color:#4ade80">Login Berhasil</h1>
  <p>{greeting}, <strong>{name}</strong></p>
  <p class="meta">{email}</p>
  <p style="margin-top:20px">Buka Telegram dan kirim <strong>/start</strong> ke bot untuk mulai.</p>
  <p class="dim">Halaman ini bisa ditutup.</p>
</div>""")


def _error_page(message: str) -> str:
    return _page(f"""
<div class="card">
  <div class="icon">&#10007;</div>
  <h1 class="err">Login Gagal</h1>
  <p>{message}</p>
  <a class="btn" href="/auth/google/login">Coba Lagi</a>
  <p class="dim" style="margin-top:20px">Atau tutup halaman ini dan coba dari terminal.</p>
</div>""")


def _login_page() -> str:
    return _page("""
<div class="card">
  <div class="icon">&#128100;</div>
  <h1>AI Agent</h1>
  <p>Login untuk mengakses dan mendaftarkan akun kamu.</p>
  <a class="btn" href="/auth/google/login">Login dengan Google</a>
  <p class="dim" style="margin-top:20px">Akun Google kamu digunakan hanya untuk verifikasi identitas.</p>
</div>""")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    """Landing page — tampilkan tombol 'Login dengan Google' atau error jika tidak dikonfigurasi."""
    if not settings.google_client_id or not settings.google_client_secret:
        return HTMLResponse(
            _error_page("Google OAuth belum dikonfigurasi di server.<br>Isi GOOGLE_CLIENT_ID dan GOOGLE_CLIENT_SECRET di .env."),
            status_code=503,
        )
    return HTMLResponse(_login_page())


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    """Redirect ke Google OAuth consent screen."""
    if not settings.google_client_id or not settings.google_client_secret:
        return RedirectResponse(url="/auth/login")

    _purge_expired_states()
    state = secrets.token_urlsafe(16)
    _pending_states[state] = datetime.now(UTC)

    params = urllib.parse.urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })

    return RedirectResponse(url=f"{_GOOGLE_AUTH_URL}?{params}")


@router.get("/google/callback", response_class=HTMLResponse)
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """Handle callback dari Google, buat/update user di DB."""
    if error:
        return HTMLResponse(_error_page(f"Google menolak login: {error}"), status_code=400)

    if not code or not state:
        return HTMLResponse(_error_page("Parameter tidak lengkap."), status_code=400)

    if state not in _pending_states:
        return HTMLResponse(_error_page("State tidak valid atau sudah kedaluwarsa. Silakan login ulang."), status_code=400)

    del _pending_states[state]

    # Exchange code → access token
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        token_data: dict[str, Any] = token_resp.json()

    access_token = str(token_data.get("access_token", ""))
    if not access_token:
        return HTMLResponse(_error_page("Gagal mendapatkan access token dari Google."), status_code=400)

    # Get user info
    async with httpx.AsyncClient(timeout=10) as client:
        info_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_info: dict[str, Any] = info_resp.json()

    email = str(user_info.get("email", ""))
    name = str(user_info.get("name", ""))

    if not email:
        return HTMLResponse(_error_page("Email tidak ditemukan di akun Google."), status_code=400)

    # Upsert user in DB
    from app.adapters.database.repositories import ControlPlaneRepository
    from app.adapters.database.session import (
        create_database_engine,
        create_session_factory,
        session_scope,
    )

    engine = create_database_engine(settings.database_url)
    factory = create_session_factory(engine)

    is_new = False
    with session_scope(factory) as session:
        repo = ControlPlaneRepository(session)
        user = repo.get_user_by_email(email)
        if user is None:
            repo.create_user(display_name=name, email=email)
            is_new = True

    return HTMLResponse(_success_page(name, email, is_new))
