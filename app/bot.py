from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import requests

from app.config import settings
from app.handlers.auth import (
    deny_if_unauthorized,
    is_authorized,
    resolve_user_id_from_telegram,
)
from app.handlers.chat import chat_with_qwen, run_manual_command
from app.handlers.delegation import handle_agent_delegation as _handle_agent_delegation
from app.handlers.delegation import handle_pair_code as _handle_pair_code
from app.handlers.formatting import format_output, format_telegram_user
from app.handlers.project import get_project_store
from app.orchestrator.approval import PendingPlanStore

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

# Re-export for composition.py (#22) and approval handler
pending_plans = PendingPlanStore()

_HELP_TEXT = (
    "Perintah yang tersedia:\n\n"
    "Chat natural:\n"
    "  cek status server\n"
    "  cek ram / cek disk\n"
    "  docker yang jalan apa aja\n"
    "  git status\n\n"
    "Agent CLI:\n"
    "  /agents — lihat agent terdaftar\n"
    "  /codex <instruksi>\n"
    "  /claude <instruksi>\n\n"
    "Terminal:\n"
    "  /tools — lihat tools aktif\n"
    "  /tool <command>\n\n"
    "Project:\n"
    "  /project — project aktif\n"
    "  /projects — daftar semua\n"
    "  /project_add <nama> <path>\n\n"
    "Lainnya:\n"
    "  /cmd <shell command>\n"
    "  /ask <pertanyaan>\n"
    "  /whoami — lihat Telegram ID\n"
    "  /reset — reset riwayat chat"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot ini private — hanya operator (di ADMIN_USER_IDS) yang bisa pakai."""
    if update.message is None or update.effective_user is None:
        return

    tg_user = update.effective_user
    args = context.args or []

    if not is_authorized(update):
        await update.message.reply_text(
            "Bot ini private — hanya bisa dipakai oleh pemilik server.\n\n"
            "Kalau kamu ingin install AI Agent untuk dirimu sendiri, "
            "deploy backend + bot Telegram sendiri. Lihat README di "
            "github.com/codinginid/ai-agent.",
        )
        return

    if args and args[0].startswith("TG-"):
        await _handle_pair_code(update, tg_user, args[0])
        return

    await update.message.reply_text(
        "Hai! Bot ini sudah aktif untuk akun kamu.\n\n"
        "Untuk hubungkan akun Telegram ini ke akun TUI:\n"
        "  1. Buka TUI di komputer kamu\n"
        "  2. Login Google dulu (`/login`)\n"
        "  3. Lalu `/pair-telegram` — scan QR atau klik link\n\n"
        + _HELP_TEXT
    )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(format_telegram_user(update))  # type: ignore[union-attr]


async def cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    command_text = " ".join(context.args or [])
    output = run_manual_command(command_text)
    await update.message.reply_text(f"Command:\n{command_text}\n\nResult:\n{output}")  # type: ignore[union-attr]


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    question = " ".join(context.args or []).strip()
    if not question:
        await update.message.reply_text("Pakai format: /ask pertanyaan kamu")  # type: ignore[union-attr]
        return

    await _reply_chat(update, context, question)


async def _reply_chat(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str
) -> None:
    try:
        reply = chat_with_qwen(user_text, context)
    except requests.RequestException as exc:
        await update.message.reply_text(f"Gagal menghubungi Qwen/Ollama: {exc}")  # type: ignore[union-attr]
        return
    except Exception as exc:
        await update.message.reply_text(f"Gagal membuat jawaban chat: {exc}")  # type: ignore[union-attr]
        return

    await update.message.reply_text(format_output(reply))  # type: ignore[union-attr]


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    user_text = update.message.text.strip()  # type: ignore[union-attr]
    if not user_text:
        return

    tg_user = update.effective_user
    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    project_store = get_project_store()
    active_project = project_store.get_active_project(chat_id, settings.project_dir)

    user_id = resolve_user_id_from_telegram(tg_user.id if tg_user else None)
    if user_id is None:
        await update.message.reply_text(  # type: ignore[union-attr]
            "Akun belum terdaftar. Kirim /start dulu untuk auto-register."
        )
        return

    from app.composition import build_use_case
    from app.domain.messaging import ChatEventType, MessageContext

    use_case = build_use_case()
    ctx = MessageContext(
        user_id=user_id,
        conversation_id=str(chat_id),
        project_id=active_project.id,
        project_root=Path(active_project.root_path),
        project_name=active_project.name,
        telegram_user_id=tg_user.id if tg_user else None,
        extra={
            "telegram_username": (
                f"@{tg_user.username}" if tg_user and tg_user.username else "-"
            )
        },
    )

    text_chunks: list[str] = []
    final_sent = False

    try:
        for event in use_case.handle(user_text, ctx):
            if event.type == ChatEventType.APPROVAL_REQUIRED:
                summary = event.payload["summary"]
                plan_id = event.payload["plan_id"]
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"{summary}\n\n"
                    f"Konfirmasi: /approve {plan_id}\n"
                    f"Batalkan:   /reject {plan_id}\n"
                    f"(kedaluwarsa dalam 5 menit)"
                )
                final_sent = True
            elif event.type == ChatEventType.TEXT_CHUNK:
                text_chunks.append(event.payload["text"])
            elif event.type == ChatEventType.FINAL:
                final_text = event.payload.get("text") or "".join(text_chunks)
                if final_text.strip():
                    await update.message.reply_text(format_output(final_text))  # type: ignore[union-attr]
                final_sent = True
            elif event.type == ChatEventType.ERROR:
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"Maaf, terjadi error: {event.payload['message']}"
                )
                final_sent = True
            elif event.type == ChatEventType.DELEGATE_TO_AGENT:
                await _handle_agent_delegation(
                    update,
                    user_id=user_id,
                    agent=str(event.payload.get("agent", "codex")),
                    prompt=str(event.payload.get("prompt", "")),
                )
                final_sent = True
    except Exception as exc:  # defensive safety net — use case sudah handle internal errors
        await update.message.reply_text(f"Internal error: {exc}")  # type: ignore[union-attr]
        return

    if not final_sent and text_chunks:
        await update.message.reply_text(format_output("".join(text_chunks)))  # type: ignore[union-attr]


