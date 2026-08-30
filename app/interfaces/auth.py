from __future__ import annotations

import contextlib
import logging
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select

from app.adapters.database.models import UserModel
from app.adapters.database.repositories import ControlPlaneRepository, DatabaseConflictError
from app.adapters.database.session import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from app.adapters.sessions import UserSessionRepository
from app.config import settings
from app.domain.providers import ALL_PROVIDERS
from app.interfaces.auth_pages import (
    error_page as _error_page,
)
from app.interfaces.auth_pages import (
    login_page as _login_page,
)
from app.interfaces.auth_pages import (
    success_page as _success_page,
)
from app.interfaces.auth_pages import (
    tui_login_page as _tui_login_page,
)
from app.interfaces.auth_pages import (
    tui_success_page as _tui_success_page,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"
_SCOPES = "openid email profile"
_STATE_TTL = timedelta(minutes=15)
_TUI_CODE_TTL = timedelta(minutes=15)
# Setelah pair code di-mark "paired", kasih waktu lebih panjang sampai TUI sempat
# polling — supaya OAuth user yang lambat tidak kehilangan token-nya.
_TUI_PAIRED_TTL = timedelta(hours=1)

PairStatus = Literal["pending", "paired", "expired"]


@dataclass
class _PendingState:
    created_at: datetime
    tui_code: str | None = None


@dataclass
class _PairCode:
    created_at: datetime
    status: PairStatus = "pending"
    session_token: str | None = None
    user_id: str | None = None


# In-memory store — single process dev; pakai Redis di produksi multi-instance.
_pending_states: dict[str, _PendingState] = {}
_pair_codes: dict[str, _PairCode] = {}

# Telegram pair codes disimpan di Redis supaya tidak hilang saat container restart.
_TG_PAIR_TTL: int = int(_TUI_CODE_TTL.total_seconds())  # 900 detik


def _redirect_uri() -> str:
    return f"{settings.app_url}/auth/google/callback"


def _purge_expired() -> None:
    now = datetime.now(UTC)
    for k in [k for k, v in _pending_states.items() if now - v.created_at > _STATE_TTL]:
        del _pending_states[k]

    pair_to_drop: list[str] = []
    for k, v in _pair_codes.items():
        age = now - v.created_at
        ttl = _TUI_PAIRED_TTL if v.status == "paired" else _TUI_CODE_TTL
        if age > ttl:
            pair_to_drop.append(k)
    for k in pair_to_drop:
        del _pair_codes[k]

    # _tg_pair_codes sudah di Redis — TTL diurus otomatis, tidak perlu purge manual.


def _new_pair_code() -> str:
    """Format ``AI-XXXXXX`` — pendek, mudah dibaca/diketik."""
    raw = secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:6].upper()
    return f"AI-{raw}"


def _new_tg_pair_code() -> str:
    """Format ``TG-XXXXXX`` untuk Telegram /start deep link."""
    raw = secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:6].upper()
    return f"TG-{raw}"


async def claim_telegram_pair_code_async(code: str) -> str | None:
    """Klaim Telegram pair code dari Redis → return user_id. One-shot (key dihapus)."""
    from app.adapters.redis_client import get_client, k_tg_pair
    redis = get_client()
    key = k_tg_pair(code.strip().upper())
    user_id = await redis.getdel(key)
    if user_id is None:
        return None
    return user_id.decode() if isinstance(user_id, bytes) else str(user_id)


# Cached engine + factory — bikin baru tiap request mahal di Neon Postgres
# (SSL handshake ~5 detik), dan SQLAlchemy connection pool memang dirancang
# supaya engine di-share lifetime aplikasi.
_cached_factory: Any = None


def _session_factory_lazy() -> Any:
    global _cached_factory
    if _cached_factory is None:
        engine = create_database_engine(settings.database_url)
        _cached_factory = create_session_factory(engine)
    return _cached_factory


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/config")
async def auth_config() -> JSONResponse:
    """Publik: kemampuan login yang tersedia — web memutuskan tombol mana yang ditampilkan."""
    return JSONResponse(
        {"google_oauth": bool(settings.google_client_id and settings.google_client_secret)}
    )


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
async def google_login(tui_code: str | None = None) -> RedirectResponse:
    """Redirect ke Google OAuth consent screen.

    Kalau ``tui_code`` ada (dari TUI login flow), state akan ingat code itu —
    callback akan kaitkan session token ke code supaya TUI bisa polling.
    """
    if not settings.google_client_id or not settings.google_client_secret:
        return RedirectResponse(url="/auth/login")

    _purge_expired()
    state = secrets.token_urlsafe(16)
    _pending_states[state] = _PendingState(
        created_at=datetime.now(UTC),
        tui_code=tui_code if tui_code in _pair_codes else None,
    )

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

    pending = _pending_states.pop(state, None)
    if pending is None:
        return HTMLResponse(_error_page("State tidak valid atau sudah kedaluwarsa. Silakan login ulang."), status_code=400)
    tui_code = pending.tui_code

    # trust_env=False: HTTPS_PROXY di .env ditujukan untuk bot di VPS, bukan untuk
    # callback OAuth yang harus langsung menjangkau Google.
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
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
    except httpx.HTTPError as exc:
        logger.exception("Google token exchange failed")
        return HTMLResponse(
            _error_page(f"Tidak bisa menghubungi Google untuk tukar token: {exc}"),
            status_code=502,
        )

    access_token = str(token_data.get("access_token", ""))
    if not access_token:
        logger.warning("Google token response missing access_token: %s", token_data)
        return HTMLResponse(
            _error_page(f"Gagal mendapatkan access token dari Google: {token_data.get('error_description') or token_data.get('error') or 'unknown'}"),
            status_code=400,
        )

    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            info_resp = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_info: dict[str, Any] = info_resp.json()
    except httpx.HTTPError as exc:
        logger.exception("Google userinfo fetch failed")
        return HTMLResponse(
            _error_page(f"Tidak bisa mengambil profil Google: {exc}"),
            status_code=502,
        )

    email = str(user_info.get("email", "")).strip()
    name = str(user_info.get("name", "")).strip()

    if not email:
        logger.warning("Google userinfo missing email: %s", user_info)
        return HTMLResponse(_error_page("Email tidak ditemukan di akun Google."), status_code=400)

    # Allowlist gate — akses ditolak kalau email tidak terdaftar (bila allowlist
    # diisi). Fail-closed sederhana; dicek sebelum upsert supaya tak buat user.
    if not _email_allowed(email):
        logger.warning("Login ditolak — email tidak di allowlist: %s", email)
        return HTMLResponse(
            _error_page("Email kamu tidak diizinkan mengakses sistem ini."),
            status_code=403,
        )

    # Upsert user in DB + (kalau TUI flow) buat session
    tui_pair_succeeded = False
    try:
        factory = _session_factory_lazy()

        is_new = False
        user_id: str | None = None
        with session_scope(factory) as session:
            repo = ControlPlaneRepository(session)
            user = repo.get_user_by_email(email)
            if user is None:
                user = repo.create_user(display_name=name, email=email)
                is_new = True
                logger.info("Created new user via Google OAuth: email=%s name=%s", email, name)
            else:
                logger.info("Existing user logged in via Google OAuth: email=%s", email)
            user_id = user.id

        if tui_code and user_id:
            entry = _pair_codes.get(tui_code)
            if entry is None:
                logger.warning(
                    "TUI pair code %s tidak ditemukan saat callback — mungkin "
                    "sudah expired/purged. User upsert tetap jalan tapi TUI "
                    "tidak akan dapat session.",
                    tui_code,
                )
            else:
                sessions = UserSessionRepository(factory)
                session_info = sessions.create(user_id=user_id, user_agent="ai-agent-tui")
                entry.status = "paired"
                entry.session_token = session_info.token
                entry.user_id = user_id
                tui_pair_succeeded = True
                logger.info("TUI pair code %s linked to user %s", tui_code, user_id)
    except Exception as exc:
        logger.exception("Failed to upsert user from Google OAuth")
        return HTMLResponse(
            _error_page(f"Login berhasil di Google tapi gagal simpan ke database: {exc}"),
            status_code=500,
        )

    if tui_code and not tui_pair_succeeded:
        # User Google login berhasil tapi pair code sudah hilang — TUI sedang
        # tidak menunggu code ini. Minta user retry /login.
        return HTMLResponse(
            _error_page(
                "Login Google sukses, tapi sesi TUI sudah kedaluwarsa "
                "(>15 menit). Akun kamu sudah tersimpan — kembali ke terminal, "
                "ketik <strong>/login</strong> lagi untuk dapat session token."
            ),
            status_code=410,
        )
    if tui_code:
        return HTMLResponse(_tui_success_page(name, email))
    return HTMLResponse(_success_page(name, email, is_new))


# ── TUI login flow ────────────────────────────────────────────────────────────

@router.post("/tui/start")
async def tui_start() -> JSONResponse:
    """TUI minta kode pairing baru. Return code + login URL."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth belum dikonfigurasi di server",
        )
    _purge_expired()
    code = _new_pair_code()
    while code in _pair_codes:
        code = _new_pair_code()
    _pair_codes[code] = _PairCode(created_at=datetime.now(UTC))
    login_url = f"{settings.app_url}/auth/tui-login?code={urllib.parse.quote(code)}"
    return JSONResponse(
        {
            "code": code,
            "login_url": login_url,
            "expires_in_sec": int(_TUI_CODE_TTL.total_seconds()),
        }
    )


@router.get("/tui-login", response_class=HTMLResponse)
async def tui_login(code: str | None = None) -> HTMLResponse:
    """Halaman browser yang user buka — ada tombol 'Login dengan Google'."""
    _purge_expired()
    if not code or code not in _pair_codes:
        return HTMLResponse(
            _error_page("Kode pair tidak valid atau sudah kedaluwarsa."),
            status_code=400,
        )
    return HTMLResponse(_tui_login_page(code))


@router.post("/tui/poll")
async def tui_poll(payload: Annotated[dict[str, str], Body(...)]) -> JSONResponse:
    """TUI polling: kalau sudah paired, return session_token."""
    code = payload.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    _purge_expired()
    entry = _pair_codes.get(code)
    if entry is None:
        raise HTTPException(status_code=410, detail="code expired or unknown")
    if entry.status == "paired" and entry.session_token:
        del _pair_codes[code]
        return JSONResponse(
            {"status": "paired", "session_token": entry.session_token}
        )
    return JSONResponse({"status": "pending"}, status_code=202)


# ── Bearer session helpers ────────────────────────────────────────────────────

def _resolve_session_user(authorization: str | None) -> tuple[str, str] | None:
    """Return (user_id, token) kalau valid, else None."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    repo = UserSessionRepository(_session_factory_lazy())
    info = repo.resolve(token)
    if info is None:
        return None
    return info.user_id, info.token


@router.get("/me")
async def auth_me(authorization: str | None = Header(default=None)) -> JSONResponse:
    """Validate session token, return user info."""
    resolved = _resolve_session_user(authorization)
    if resolved is None:
        raise HTTPException(
            status_code=401,
            detail="invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id, _ = resolved
    factory = _session_factory_lazy()
    with session_scope(factory) as session:
        user = session.scalar(select(UserModel).where(UserModel.id == user_id))
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        return JSONResponse(
            {
                "user_id": user.id,
                "email": user.email,
                "display_name": user.display_name,
            }
        )


@router.put("/me/provider")
async def set_my_provider(
    payload: Annotated[dict[str, Any], Body(...)],
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Persist pilihan provider 'otak' user — TANPA efek samping lain (key
    tak pernah dikirim/di-persist di sini, hanya nama provider).

    Body: {"provider": "...", "as_email": "..."} — ``as_email`` cuma dipakai
    kalau caller admin token (pola sama seperti ``/chat/send``).
    """
    from app.adapters.user_provider_config import UserProviderConfigRepository
    from app.interfaces.chat import _resolve_admin_target, _resolve_caller

    caller_user_id, mode = _resolve_caller(authorization)
    if mode == "admin":
        as_email = str(payload.get("as_email", "") or "")
        if not as_email:
            raise HTTPException(status_code=400, detail="admin token requires 'as_email' field")
        user_id = _resolve_admin_target(as_email)
    else:
        user_id = caller_user_id

    provider = str(payload.get("provider", "")).strip().lower()
    if provider not in ALL_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"provider harus salah satu: {sorted(ALL_PROVIDERS)}",
        )

    UserProviderConfigRepository(_session_factory_lazy()).set(user_id, provider)
    return JSONResponse({"ok": True, "provider": provider})


@router.post("/tui/logout")
async def tui_logout(authorization: str | None = Header(default=None)) -> JSONResponse:
    """Revoke current session."""
    resolved = _resolve_session_user(authorization)
    if resolved is None:
        raise HTTPException(status_code=401, detail="not logged in")
    _, token = resolved
    repo = UserSessionRepository(_session_factory_lazy())
    repo.revoke(token)
    return JSONResponse({"revoked": True})


# ── Telegram pair ────────────────────────────────────────────────────────────

@router.post("/telegram/pair-init")
async def telegram_pair_init(
    payload: Annotated[dict[str, Any], Body(default_factory=dict)],
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """User yang sudah login Google minta pair code Telegram.

    Body (optional): {"bot_username": "nama_bot"}  — TUI fetch via getMe lalu kirim ke sini.
    Return: {code, deep_link (kalau bot_username tersedia), expires_in_sec}
    """
    resolved = _resolve_session_user(authorization)
    if resolved is None:
        raise HTTPException(
            status_code=401,
            detail="login dulu via /login di TUI",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id, _ = resolved

    from app.adapters.redis_client import get_client, k_tg_pair
    redis = get_client()

    _purge_expired()
    code = _new_tg_pair_code()
    # Pastikan unik — Redis SET NX (not exists)
    while not await redis.set(k_tg_pair(code), user_id, ex=_TG_PAIR_TTL, nx=True):
        code = _new_tg_pair_code()

    # bot_username dikirim TUI setelah validasi token via Telegram getMe.
    # Kalau tidak ada, return code saja — TUI tampilkan instruksi manual.
    bot_username = str(payload.get("bot_username", "")).strip().lstrip("@")
    result: dict[str, Any] = {
        "code": code,
        "expires_in_sec": int(_TUI_CODE_TTL.total_seconds()),
    }
    if bot_username:
        result["deep_link"] = f"https://t.me/{bot_username}?start={urllib.parse.quote(code)}"
        result["bot_username"] = bot_username

    return JSONResponse(result)


# ── Telegram adapter endpoints ───────────────────────────────────────────────
# Dipakai oleh telegram-adapter (proses terpisah) untuk:
# 1. Menyelesaikan pairing setelah user klik deep link
# 2. Resolve Telegram user_id → Core user sebelum tiap pesan

def _email_allowed(email: str) -> bool:
    """Allowlist email — kosong = terbuka (dev); diisi = hanya email terdaftar."""
    allowed = settings.allowed_emails
    return not allowed or email.strip().lower() in allowed


def _require_admin_token(authorization: str | None) -> None:
    """Raise kalau bukan admin token. FAIL-CLOSED: admin_token kosong =
    admin dinonaktifkan (503), bukan skip check (dulu fail-open → terbuka)."""
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="admin disabled: ADMIN_TOKEN belum diset")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="admin token required")
    token = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(token, settings.admin_token):
        raise HTTPException(status_code=401, detail="invalid admin token")


@router.post("/telegram/pair-complete")
async def telegram_pair_complete(
    payload: Annotated[dict[str, Any], Body(...)],
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Telegram adapter memanggil ini setelah user kirim /start <code>.

    Body: {code, telegram_user_id, username?, first_name?}
    Return: {user_id, email, display_name}
    """
    _require_admin_token(authorization)

    code = str(payload.get("code", "")).strip()
    telegram_user_id = int(payload.get("telegram_user_id", 0))
    if not code or not telegram_user_id:
        raise HTTPException(status_code=400, detail="code dan telegram_user_id wajib diisi")

    user_id = await claim_telegram_pair_code_async(code)
    if user_id is None:
        raise HTTPException(status_code=410, detail="code tidak valid atau sudah kedaluwarsa")

    factory = _session_factory_lazy()
    try:
        with session_scope(factory) as session:
            repo = ControlPlaneRepository(session)
            with contextlib.suppress(DatabaseConflictError):
                repo.link_telegram_account(
                    user_id=user_id,
                    telegram_user_id=telegram_user_id,
                    username=str(payload.get("username", "") or ""),
                    first_name=str(payload.get("first_name", "") or ""),
                )

        with session_scope(factory) as session:
            user = session.scalar(select(UserModel).where(UserModel.id == user_id))
            if user is None:
                raise HTTPException(status_code=404, detail="user not found")
            return JSONResponse({
                "user_id": user.id,
                "email": user.email,
                "display_name": user.display_name,
            })
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("telegram pair-complete failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/telegram/user/{telegram_user_id}")
async def telegram_resolve_user(
    telegram_user_id: int,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Telegram adapter cek apakah Telegram user sudah linked ke Core user.

    Return: {user_id, email, display_name}
    404 kalau belum pernah pair.
    """
    _require_admin_token(authorization)

    factory = _session_factory_lazy()
    with session_scope(factory) as session:
        repo = ControlPlaneRepository(session)
        identity = repo.resolve_by_telegram_user_id(telegram_user_id)
        if identity is None:
            raise HTTPException(status_code=404, detail="telegram user belum pair")

        user = session.scalar(select(UserModel).where(UserModel.id == identity.user_id))
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")

        return JSONResponse({
            "user_id": user.id,
            "email": user.email,
            "display_name": user.display_name,
        })


# ── Per-user agent configuration ─────────────────────────────────────────────

@router.get("/me/agents")
async def list_my_agents(
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """List konfigurasi agent (Codex/Claude/GLM) untuk user yang lagi login."""
    resolved = _resolve_session_user(authorization)
    if resolved is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user_id, _ = resolved

    from app.adapters.agent_configs import (
        DEFAULT_ROLE,
        KNOWN_AGENTS,
        UserAgentConfigRepository,
    )
    from app.adapters.redis_client import get_client, k_caps

    repo = UserAgentConfigRepository(_session_factory_lazy())
    existing = {c.agent_id: c for c in repo.list(user_id)}

    redis = get_client()
    # Tampilkan semua agent yang dikenal — yang belum di-config dianggap disabled.
    # Plus jumlah worker yang punya CLI installed (dari capabilities advertise).
    agents = []
    for agent_id in KNOWN_AGENTS:
        cfg = existing.get(agent_id)
        installed_workers = await redis.scard(k_caps(user_id, agent_id))  # type: ignore[misc]
        agents.append({
            "agent_id": agent_id,
            "enabled": bool(cfg and cfg.enabled),
            "role": cfg.role if cfg else DEFAULT_ROLE.get(agent_id),
            "model": cfg.model if cfg else None,
            "installed_on_workers": int(installed_workers or 0),
        })
    return JSONResponse({"agents": agents})


@router.get("/me/devices")
async def list_my_devices(
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """List semua device yang pernah connect sebagai worker untuk user ini."""
    resolved = _resolve_session_user(authorization)
    if resolved is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user_id, _ = resolved

    from app.adapters.database.repositories import ControlPlaneRepository

    factory = _session_factory_lazy()
    with factory() as session:
        repo = ControlPlaneRepository(session)
        devices = repo.list_devices(user_id)
        return JSONResponse({
            "devices": [
                {
                    "device_id": d.id,
                    "name": d.name,
                    "status": d.status,
                    "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
                    "created_at": d.created_at.isoformat(),
                }
                for d in devices
            ]
        })


@router.get("/me/devices/{device_id}/agents")
async def list_device_agents(
    device_id: str,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """List agent integrations yang terdeteksi di sebuah device."""
    resolved = _resolve_session_user(authorization)
    if resolved is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user_id, _ = resolved

    from app.adapters.database.repositories import ControlPlaneRepository

    factory = _session_factory_lazy()
    with factory() as session:
        repo = ControlPlaneRepository(session)
        device = repo.get_device(device_id, user_id)
        if device is None:
            raise HTTPException(status_code=404, detail="device not found")
        integrations = repo.list_agent_integrations(device_id)
        return JSONResponse({
            "device_id": device_id,
            "device_name": device.name,
            "agents": [
                {
                    "agent_id": i.agent_id,
                    "display_name": i.display_name,
                    "provider": i.provider,
                    "installed": i.installed,
                    "enabled": i.enabled,
                    "ready": i.ready,
                    "status": i.status,
                    "version": i.version,
                    "executable": i.executable,
                    "last_probe_at": i.last_probe_at.isoformat() if i.last_probe_at else None,
                }
                for i in integrations
            ],
        })


@router.put("/me/agents/{agent_id}")
async def upsert_my_agent(
    agent_id: str,
    payload: Annotated[dict[str, Any], Body(...)],
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Update konfigurasi agent untuk user.

    Body fields (semua optional, hanya yang diisi yang di-update):
    - ``enabled``: bool
    - ``role``: "engineer" | "reviewer" | "architect" | null
    - ``model``: str | null
    """
    resolved = _resolve_session_user(authorization)
    if resolved is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user_id, _ = resolved

    from app.adapters.agent_configs import (
        KNOWN_AGENTS,
        VALID_ROLES,
        UserAgentConfigRepository,
    )

    if agent_id not in KNOWN_AGENTS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown agent_id '{agent_id}'. Allowed: {', '.join(KNOWN_AGENTS)}",
        )
    role = payload.get("role")
    if role is not None and role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid role '{role}'. Allowed: {', '.join(VALID_ROLES)}",
        )

    repo = UserAgentConfigRepository(_session_factory_lazy())
    cfg = repo.upsert(
        user_id=user_id,
        agent_id=agent_id,
        enabled=payload.get("enabled"),
        role=role,
        model=payload.get("model"),
    )
    return JSONResponse({
        "agent_id": cfg.agent_id,
        "enabled": cfg.enabled,
        "role": cfg.role,
        "model": cfg.model,
    })
