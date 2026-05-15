from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.handlers.agents import run_claude_agent, run_codex_agent
from app.handlers.auth import deny_if_unauthorized, get_db_session_factory
from app.handlers.formatting import format_output
from app.handlers.terminal import (
    btop_snapshot,
    run_terminal_command,
    spf_listing,
    terminal_status_text,
)

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


async def agents_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Per-user agent config — list/toggle/set role/set model.

    Usage:
        /agents                       — list semua agent
        /agents <name> on|off         — enable/disable
        /agents <name> role <role>    — engineer/reviewer/architect
        /agents <name> model <model>  — override default model
    """
    if await deny_if_unauthorized(update):
        return

    from app.handlers.auth import resolve_user_id_from_telegram

    tg_user = update.effective_user
    user_id = resolve_user_id_from_telegram(tg_user.id if tg_user else None)
    if user_id is None:
        await update.message.reply_text(  # type: ignore[union-attr]
            "Akun belum terdaftar. /start dulu, atau pair via /pair-telegram di TUI."
        )
        return

    from app.adapters.agent_configs import (
        DEFAULT_ROLE,
        KNOWN_AGENTS,
        VALID_ROLES,
        UserAgentConfigRepository,
    )

    repo = UserAgentConfigRepository(get_db_session_factory())  # type: ignore[arg-type]
    args = context.args or []

    if not args:
        existing = {c.agent_id: c for c in repo.list(user_id)}
        lines = ["Agent Config:"]
        for aid in KNOWN_AGENTS:
            cfg = existing.get(aid)
            en = "✓" if (cfg and cfg.enabled) else "✗"
            role = (cfg.role if cfg else None) or DEFAULT_ROLE.get(aid) or "-"
            model = (cfg.model if cfg else None) or "(default)"
            lines.append(f"  {en} {aid:<8} role={role:<10} model={model}")
        lines.append("")
        lines.append("Usage:")
        lines.append("  /agents codex on")
        lines.append("  /agents codex role engineer")
        lines.append("  /agents codex model gpt-4o-mini")
        await update.message.reply_text("\n".join(lines))  # type: ignore[union-attr]
        return

    name = args[0].lower()
    if name not in KNOWN_AGENTS:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Agent tidak dikenal: {name}. Allowed: {', '.join(KNOWN_AGENTS)}"
        )
        return
    if len(args) < 2:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Usage: /agents {name} on|off | role <role> | model <model>"
        )
        return

    op = args[1].lower()
    try:
        if op in ("on", "off", "enable", "disable"):
            cfg = repo.upsert(user_id, name, enabled=(op in ("on", "enable")))
            await update.message.reply_text(  # type: ignore[union-attr]
                f"✓ {cfg.agent_id}: enabled={cfg.enabled} role={cfg.role or '-'}"
            )
        elif op == "role" and len(args) >= 3:
            role = args[2].lower()
            if role not in VALID_ROLES:
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"Role invalid: {role}. Allowed: {', '.join(VALID_ROLES)}"
                )
                return
            cfg = repo.upsert(user_id, name, role=role)
            await update.message.reply_text(f"✓ {cfg.agent_id}: role={cfg.role}")  # type: ignore[union-attr]
        elif op == "model" and len(args) >= 3:
            cfg = repo.upsert(user_id, name, model=args[2])
            await update.message.reply_text(f"✓ {cfg.agent_id}: model={cfg.model}")  # type: ignore[union-attr]
        else:
            await update.message.reply_text(f"Op tidak dikenal: {op}")  # type: ignore[union-attr]
    except Exception as exc:
        await update.message.reply_text(f"Gagal update: {exc}")  # type: ignore[union-attr]


async def tools_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    await update.message.reply_text(format_output(terminal_status_text()))  # type: ignore[union-attr]


async def tool_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    command_text = " ".join(context.args or []).strip()
    if not command_text:
        await update.message.reply_text(  # type: ignore[union-attr]
            "Pakai format: /tool command args, contoh: /tool fastfetch"
        )
        return

    result = await asyncio.to_thread(run_terminal_command, command_text)
    await update.message.reply_text(f"Tool result:\n\n{format_output(result)}")  # type: ignore[union-attr]


async def btop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    result = await asyncio.to_thread(btop_snapshot)
    await update.message.reply_text(format_output(result))  # type: ignore[union-attr]


async def spf_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    path_text = " ".join(context.args or []).strip()
    result = await asyncio.to_thread(spf_listing, path_text)
    await update.message.reply_text(format_output(result))  # type: ignore[union-attr]


async def codex_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    prompt = " ".join(context.args or []).strip()
    if not prompt:
        await update.message.reply_text("Pakai format: /codex instruksi kamu")  # type: ignore[union-attr]
        return

    await update.message.reply_text("Menjalankan Codex...")  # type: ignore[union-attr]
    result = await asyncio.to_thread(run_codex_agent, prompt)
    await update.message.reply_text(f"Codex result:\n\n{format_output(result)}")  # type: ignore[union-attr]


async def claude_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    prompt = " ".join(context.args or []).strip()
    if not prompt:
        await update.message.reply_text("Pakai format: /claude instruksi kamu")  # type: ignore[union-attr]
        return

    await update.message.reply_text("Menjalankan Claude...")  # type: ignore[union-attr]
    result = await asyncio.to_thread(run_claude_agent, prompt)
    await update.message.reply_text(f"Claude result:\n\n{format_output(result)}")  # type: ignore[union-attr]


async def reset_chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    context.user_data["chat_history"] = []  # type: ignore[index]
    await update.message.reply_text("Riwayat chat sudah direset.")  # type: ignore[union-attr]
