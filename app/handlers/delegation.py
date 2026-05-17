from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.database.repositories import ControlPlaneRepository, DatabaseConflictError
from app.adapters.database.session import session_scope
from app.handlers.auth import get_db_session_factory
from app.handlers.formatting import format_output

if TYPE_CHECKING:
    from telegram import Update, User


async def handle_pair_code(update: Update, tg_user: User | None, code: str) -> None:
    """Klaim code TUI pairing → link telegram_user_id ke user_id yang sudah login."""
    from sqlalchemy import select

    from app.adapters.database.models import UserModel
    from app.interfaces.auth import claim_telegram_pair_code_async

    if tg_user is None:
        return

    user_id = await claim_telegram_pair_code_async(code)
    if user_id is None:
        await update.message.reply_text(  # type: ignore[union-attr]
            "Kode pair tidak valid atau sudah kedaluwarsa.\n"
            "Buka TUI di komputer dan jalankan /pair-telegram untuk dapat kode baru."
        )
        return

    try:
        with session_scope(get_db_session_factory()) as session:
            repo = ControlPlaneRepository(session)
            existing = repo.resolve_by_telegram_user_id(tg_user.id)
            if existing is not None:
                if existing.user_id == user_id:
                    await update.message.reply_text(  # type: ignore[union-attr]
                        "Akun Telegram kamu sudah ter-link ke user ini."
                    )
                    return
                old_user = session.scalar(
                    select(UserModel).where(UserModel.id == existing.user_id)
                )
                if old_user is not None and not old_user.email:
                    session.delete(old_user)
                    session.flush()
                else:
                    await update.message.reply_text(  # type: ignore[union-attr]
                        "Akun Telegram kamu sudah ter-link ke user lain (yang punya email). "
                        "Hubungi admin untuk unlink dulu."
                    )
                    return
            repo.link_telegram_account(
                user_id=user_id,
                telegram_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )
    except DatabaseConflictError:
        await update.message.reply_text(  # type: ignore[union-attr]
            "Akun Telegram kamu sudah ter-link ke user lain."
        )
        return
    except Exception as exc:
        await update.message.reply_text(f"Gagal link akun: {exc}")  # type: ignore[union-attr]
        return

    await update.message.reply_text(  # type: ignore[union-attr]
        "Berhasil terhubung. Kamu sekarang bisa pakai bot ini sebagai akun TUI kamu."
    )


async def handle_agent_delegation(
    update: Update,
    *,
    user_id: str,
    agent: str,
    prompt: str,
) -> None:
    """Forward delegate event ke worker user, kumpulin chunks, kirim ke Telegram."""
    from app.adapters.audit import log_event
    from app.interfaces.worker_ws import (
        NoWorkerAvailableError,
        dispatch_agent_job,
    )

    if not prompt:
        await update.message.reply_text("Prompt agent kosong.")  # type: ignore[union-attr]
        return

    await update.message.reply_text(f"⚙️  Delegasi ke `{agent}` di mesin kamu…")  # type: ignore[union-attr]
    await log_event(
        "agent_dispatch",
        user_id=user_id,
        agent=agent,
        prompt=prompt,
        status="started",
    )

    chunks: list[str] = []
    try:
        async for ev in dispatch_agent_job(user_id, agent, prompt):
            kind = ev.get("type", "")
            if kind == "job_queued":
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"⏳ {ev.get('message', 'queued — menunggu slot worker')}"
                )
                continue
            if kind == "job_chunk":
                chunks.append(str(ev.get("text", "")))
            elif kind == "job_done":
                summary = str(ev.get("summary", ""))
                full_output = "".join(chunks).strip()
                if len(full_output) <= 4000:
                    msg = full_output or summary
                    await update.message.reply_text(format_output(msg))  # type: ignore[union-attr]
                else:
                    await update.message.reply_text(  # type: ignore[union-attr]
                        format_output(full_output[-3800:]) + "\n\n[output dipotong]"
                    )
                if summary:
                    await update.message.reply_text(f"✓ {agent}: {summary}")  # type: ignore[union-attr]
                await log_event(
                    "agent_done", user_id=user_id, agent=agent, status="ok", detail=summary,
                )
                return
            elif kind == "job_error":
                err = str(ev.get("message", ""))
                await update.message.reply_text(f"❌ Agent {agent} error: {err}")  # type: ignore[union-attr]
                await log_event(
                    "agent_error", user_id=user_id, agent=agent, status="error", detail=err,
                )
                return
    except NoWorkerAvailableError as exc:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"⚠️  Worker tidak tersedia: {exc}\n"
            "Buka TUI di komputer kamu supaya bisa delegasi ke agent."
        )
        await log_event(
            "agent_error", user_id=user_id, agent=agent, status="error", detail=str(exc),
        )
