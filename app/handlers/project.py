from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.config import BASE_DIR, settings
from app.handlers.auth import deny_if_unauthorized
from app.handlers.formatting import format_output
from app.handlers.process_runners import run_process
from app.memory.store import ProjectAlreadyExistsError, ProjectStore

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

_project_store = ProjectStore(BASE_DIR / "data")


def get_project_store() -> ProjectStore:
    return _project_store


async def project_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    args = context.args or []

    if not args:
        project = _project_store.get_active_project(chat_id, settings.project_dir)
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Project aktif: {project.name}\n"
            f"ID: {project.id}\n"
            f"Path: {project.root_path}\n"
            f"Deskripsi: {project.description or '-'}"
        )
        return

    name = args[0]
    found = _project_store.get_project(name)
    if found is None:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Project '{name}' tidak ditemukan.\nGunakan /projects untuk melihat daftar."
        )
        return

    _project_store.set_active_project(chat_id, found.id)
    await update.message.reply_text(  # type: ignore[union-attr]
        f"Switched ke project: {found.name}\nPath: {found.root_path}"
    )


async def projects_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    active_id = _project_store.get_active_project_id(chat_id)
    all_projects = _project_store.list_projects()

    if not all_projects:
        await update.message.reply_text("Belum ada project terdaftar.")  # type: ignore[union-attr]
        return

    lines = ["Daftar project:"]
    for p in all_projects:
        marker = " *" if p.id == active_id else ""
        lines.append(f"- {p.name} ({p.id}){marker}  →  {p.root_path}")
    lines.append("\n* = aktif saat ini")
    await update.message.reply_text("\n".join(lines))  # type: ignore[union-attr]


async def project_add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(  # type: ignore[union-attr]
            "Format: /project_add <nama> <path>\nContoh: /project_add myapp /home/ali/myapp"
        )
        return

    name = args[0]
    root_path = args[1]
    description = " ".join(args[2:]) if len(args) > 2 else ""

    try:
        project = _project_store.add_project(name, root_path, description)
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Project ditambahkan!\nNama: {project.name}\nID: {project.id}\nPath: {project.root_path}"
        )
    except ProjectAlreadyExistsError as exc:
        await update.message.reply_text(str(exc))  # type: ignore[union-attr]


async def project_info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await deny_if_unauthorized(update):
        return

    chat = update.effective_chat
    chat_id = chat.id if chat else 0
    project = _project_store.get_active_project(chat_id, settings.project_dir)
    project_path = Path(project.root_path).expanduser().resolve()

    git_info = run_process(["git", "log", "--oneline", "-3"], cwd=project_path)
    git_status = run_process(["git", "status", "--short", "--branch"], cwd=project_path)

    await update.message.reply_text(  # type: ignore[union-attr]
        format_output(
            f"Project: {project.name} ({project.id})\n"
            f"Path: {project_path}\n"
            f"Deskripsi: {project.description or '-'}\n"
            f"Dibuat: {project.created_at[:10] if project.created_at else '-'}\n\n"
            f"Git status:\n{git_status}\n\n"
            f"3 commit terakhir:\n{git_info}"
        )
    )
