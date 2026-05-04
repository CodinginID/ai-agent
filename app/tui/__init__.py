"""TUI client — full-screen Application (Gemini CLI style).

Ketik teks bebas → dikirim ke /chat/send (SSE streaming).
Ketik /help untuk daftar command.

User pertama kali jalanin: ``/login`` → scan QR / buka URL → login Google →
session token disimpan di ``~/.config/ai-agent/session.json``.

Tidak ada akses DB di sisi client. Semua state via HTTP ke backend.
"""

from app.tui._commands import parse_command
from app.tui._runner import run

__all__ = ["parse_command", "run"]
