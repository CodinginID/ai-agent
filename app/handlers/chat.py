from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

import requests  # type: ignore[import-untyped]

from app.config import settings
from app.handlers.process_runners import run_process

if TYPE_CHECKING:
    from telegram.ext import ContextTypes


def call_qwen(prompt: str) -> str:
    response = requests.post(
        settings.qwen_url,
        json={
            "model": settings.qwen_model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=60,
    )
    response.raise_for_status()
    return str(response.json()["response"]).strip()


def get_chat_history(context: ContextTypes.DEFAULT_TYPE) -> list[dict[str, str]]:
    return context.user_data.setdefault(  # type: ignore[union-attr,no-any-return]
        "chat_history", []
    )


def remember_chat(
    context: ContextTypes.DEFAULT_TYPE, user_text: str, assistant_text: str
) -> None:
    history = get_chat_history(context)
    history.append({"user": user_text, "assistant": assistant_text})
    del history[: -settings.chat_history_limit]


def build_chat_history_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    history = get_chat_history(context)
    if not history:
        return "(belum ada)"

    lines = []
    for item in history[-settings.chat_history_limit :]:
        lines.append(f"User: {item['user']}")
        lines.append(f"Assistant: {item['assistant']}")

    return "\n".join(lines)


def chat_with_qwen(user_text: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    history_text = build_chat_history_text(context)
    prompt = (
        "Kamu adalah AI-Agent App, asisten pribadi yang berjalan melalui Telegram.\n\n"
        "Peran kamu:\n"
        "- Menjawab sapaan, percakapan umum, dan pertanyaan teknis dengan natural.\n"
        "- Gunakan bahasa yang sama dengan user. Jika user memakai Indonesia, jawab Indonesia.\n"
        "- Jawab singkat, langsung, dan praktis.\n"
        "- Jika user ingin menjalankan aksi server, arahkan ke contoh natural seperti "
        "'cek status server', 'cek ram', 'cek disk', 'status docker', 'git status', "
        "atau '/cmd docker ps'.\n"
        "- Jangan mengaku sudah menjalankan command server di mode chat. Eksekusi server "
        "hanya dilakukan oleh action bot, bukan oleh jawaban chat.\n\n"
        f"Riwayat chat terakhir:\n{history_text}\n\n"
        f"User:\n{user_text}\n\nAssistant:"
    )
    reply = call_qwen(prompt)
    remember_chat(context, user_text, reply)
    return reply


def run_manual_command(command_text: str) -> str:
    try:
        parts = shlex.split(command_text)
    except ValueError as exc:
        return f"Command tidak valid: {exc}"

    if not parts:
        return "Command kosong."

    command = parts[0]
    if command not in settings.allowed_manual_commands:
        allowed = ", ".join(sorted(settings.allowed_manual_commands))
        return f"Command tidak diizinkan: {command}\nAllowed: {allowed}"

    return run_process(parts)
