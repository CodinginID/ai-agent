"""Octopus Telegram Adapter — standalone bot yang proxy ke Octopus Core.

Tidak perlu tahu user email. Setiap Telegram user harus pair dulu ke akun
Core mereka via /start <code> (code didapat dari TUI lewat /telegram pair).
Setelah pair, semua pesan otomatis dikirim atas nama user yang benar.

Config (env vars):
  TELEGRAM_BOT_TOKEN  — Telegram bot token (required)
  OCTOPUS_CORE_URL    — URL Core API, e.g. http://localhost:8080
  OCTOPUS_ADMIN_TOKEN — Admin token Core (required untuk resolve user)
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
from typing import TYPE_CHECKING

import httpx
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

if TYPE_CHECKING:
    from telegram import Update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("octopus-telegram")

# ── Config ────────────────────────────────────────────────────────────────────

def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        logger.error("Missing required env var: %s", name)
        sys.exit(1)
    return val


BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
CORE_URL = os.getenv("OCTOPUS_CORE_URL", "http://localhost:8080").rstrip("/")
ADMIN_TOKEN = _require("OCTOPUS_ADMIN_TOKEN")

_AUTH_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
MAX_TELEGRAM_CHARS = 4000

# ── Core API helpers ──────────────────────────────────────────────────────────

async def _resolve_user(telegram_user_id: int) -> dict | None:
    """Return {user_id, email, display_name} atau None kalau belum pair."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{CORE_URL}/auth/telegram/user/{telegram_user_id}",
                headers=_AUTH_HEADERS,
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("resolve_user failed: %s", exc)
        return None


async def _complete_pair(code: str, tg_user: dict) -> dict | None:
    """Kirim pair-complete ke Core. Return user info atau None kalau gagal."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{CORE_URL}/auth/telegram/pair-complete",
                headers={**_AUTH_HEADERS, "Content-Type": "application/json"},
                json={
                    "code": code,
                    "telegram_user_id": tg_user["id"],
                    "username": tg_user.get("username"),
                    "first_name": tg_user.get("first_name"),
                },
            )
        if resp.status_code == 410:
            return None  # code expired
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("pair_complete failed: %s", exc)
        return None


async def _call_core(user_email: str, user_text: str) -> tuple[str, list[str]]:
    """POST ke Core /chat/send, parse SSE. Return (final_text, status_log)."""
    headers = {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {"text": user_text, "as_email": user_email}

    final_text = ""
    status_log: list[str] = []
    event_type = ""

    async with (
        httpx.AsyncClient(timeout=120) as client,
        client.stream("POST", f"{CORE_URL}/chat/send", headers=headers, json=payload) as resp,
    ):
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("event: "):
                event_type = line[7:].strip()
                continue
            if not line.startswith("data: "):
                continue
            raw = line[6:].strip()
            if raw in ("{}", ""):
                continue
            try:
                data: dict = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if event_type == "action_started":
                action = data.get("action", "")
                cmd = str(data.get("command", data.get("path", "")))
                status_log.append(f"⚙️ `{action}`: `{cmd[:80]}`")

            elif event_type == "action_result":
                out = str(data.get("output", "")).strip()
                if out:
                    status_log.append(f"```\n{out[:300]}\n```")

            elif event_type == "retrying":
                attempt = data.get("attempt", 0)
                reason = str(data.get("reason", ""))
                status_log.append(f"🔄 Retry {attempt}: {reason[:80]}")

            elif event_type == "final":
                final_text = str(data.get("text", "")).strip()

            elif event_type == "error":
                raise RuntimeError(str(data.get("message", "unknown error")))

    return final_text, status_log

# ── Handlers ──────────────────────────────────────────────────────────────────

_NOT_PAIRED_MSG = (
    "👋 Halo! Untuk mulai, hubungkan dulu akun Octopus kamu:\n\n"
    "1. Buka Octopus TUI di terminal\n"
    "2. Ketik `/telegram pair`\n"
    "3. Scan QR atau klik link yang muncul\n\n"
    "Setelah itu kamu bisa chat langsung di sini."
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    user = update.effective_user
    if user is None:
        return

    args = context.args or []
    code = args[0].strip() if args else ""

    # /start TG-XXXXXX → complete pairing
    if code.upper().startswith("TG-"):
        tg_user = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
        }
        result = await _complete_pair(code.upper(), tg_user)
        if result is None:
            await update.message.reply_text(
                "❌ Kode pair tidak valid atau sudah kedaluwarsa.\n"
                "Kembali ke TUI dan jalankan `/telegram pair` lagi."
            )
            return
        name = result.get("display_name") or result.get("email", "")
        await update.message.reply_text(
            f"✅ Akun berhasil dihubungkan!\n\n"
            f"Halo, *{name}*! Sekarang kamu bisa chat langsung di sini.\n\n"
            "Coba ketik: `cek status server`",
            parse_mode="Markdown",
        )
        return

    # /start tanpa code → cek apakah sudah pair
    user_info = await _resolve_user(user.id)
    if user_info:
        name = user_info.get("display_name") or user_info.get("email", "")
        await update.message.reply_text(
            f"🐙 Hai *{name}*, kamu sudah terhubung ke Octopus!\n\n"
            "Ketik pesan apa saja untuk mulai.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(_NOT_PAIRED_MSG)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    if user is None:
        return

    user_info = await _resolve_user(user.id)
    if user_info is None:
        await update.message.reply_text(_NOT_PAIRED_MSG)
        return

    email = user_info.get("email", "")
    if not email:
        await update.message.reply_text("❌ Akun belum punya email — coba pair ulang.")
        return

    status_msg = await update.message.reply_text("⏳ Memproses...")

    try:
        final_text, status_log = await _call_core(email, update.message.text)
    except httpx.HTTPStatusError as exc:
        await status_msg.edit_text(f"❌ Core API error: {exc.response.status_code}")
        return
    except Exception as exc:
        await status_msg.edit_text(f"❌ {exc}")
        return

    parts: list[str] = []
    if status_log:
        parts.extend(status_log)
        parts.append("─" * 20)
    parts.append(final_text or "(tidak ada respons)")

    reply = "\n".join(parts)
    if len(reply) > MAX_TELEGRAM_CHARS:
        reply = reply[:MAX_TELEGRAM_CHARS] + "\n…(dipotong)"

    with contextlib.suppress(Exception):
        await status_msg.edit_text(reply, parse_mode="Markdown")


# ── App ───────────────────────────────────────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


if __name__ == "__main__":
    logger.info("Starting Octopus Telegram Adapter → Core: %s", CORE_URL)
    build_app().run_polling()
