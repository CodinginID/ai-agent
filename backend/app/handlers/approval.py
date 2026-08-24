from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from app.handlers.auth import deny_if_unauthorized
from app.handlers.chat import call_qwen
from app.handlers.formatting import format_output
from app.handlers.registry import action_registry
from app.intents.schemas import EXECUTABLE_ACTIONS
from app.orchestrator.approval import PendingPlanStore

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

pending_plans = PendingPlanStore()


async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Format: /approve <plan_id>")  # type: ignore[union-attr]
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    plan_id = args[0]

    pending = pending_plans.consume(plan_id, chat_id)
    if pending is None:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Plan '{plan_id}' tidak ditemukan atau sudah kedaluwarsa."
        )
        return

    action_name = pending.plan.intent
    if action_name not in EXECUTABLE_ACTIONS:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Action '{action_name}' disetujui tapi belum ada executor-nya."
        )
        return

    result = action_registry.execute(action_name, pending.action_context)

    try:
        summary = call_qwen(
            f"Ringkas output server ini dalam bahasa Indonesia yang singkat:\n{result}"
        )
    except Exception:
        summary = result

    await update.message.reply_text(  # type: ignore[union-attr]
        f"Approved & executed: {action_name}\n\n{format_output(summary)}"
    )


async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Format: /reject <plan_id>")  # type: ignore[union-attr]
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    plan_id = args[0]

    if pending_plans.cancel(plan_id, chat_id):
        await update.message.reply_text("Plan dibatalkan.")  # type: ignore[union-attr]
    else:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Plan '{plan_id}' tidak ditemukan atau sudah kedaluwarsa."
        )


async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    plans = pending_plans.list_for_chat(chat_id)

    if not plans:
        await update.message.reply_text(  # type: ignore[union-attr]
            "Tidak ada plan yang menunggu approval."
        )
        return

    lines = [f"Plan pending ({len(plans)}):"]
    for p in plans:
        sisa = int((p.expires_at - datetime.datetime.now()).total_seconds() / 60)
        lines.append(
            f"- {p.plan.plan_id[:8]}...  action: {p.plan.intent}"
            f"  (kedaluwarsa ~{sisa} menit)"
        )
        lines.append(f"  /approve {p.plan.plan_id}")
    await update.message.reply_text("\n".join(lines))  # type: ignore[union-attr]
