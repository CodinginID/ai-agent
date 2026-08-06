from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from telegram import Update


def format_telegram_user(update: Update) -> str:
    user = update.effective_user
    username = f"@{user.username}" if user and user.username else "-"
    return "\n".join(
        [
            f"Telegram user ID: {user.id if user else '-'}",
            f"Username: {username}",
            f"Admin restriction: {'nonaktif' if settings.allow_unrestricted_access else 'aktif'}",
        ]
    )


def format_output(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "(no output)"

    if len(text) <= settings.max_reply_chars:
        return text

    return text[: settings.max_reply_chars] + "\n\n...output dipotong..."


def bytes_to_gb(value: int) -> str:
    return f"{value / (1024 ** 3):.2f} GB"
