"""Local CLI interface — sama orchestrator dengan Telegram/HTTP.

Issue #7: Bisa dipakai operator di mesin lokal tanpa nyalain Telegram polling.

Subcommands:
- ``ai-agent status``                 → tampilkan project context aktif
- ``ai-agent ask "<text>"``           → jalankan use case (sama dengan chat di Telegram)
- ``ai-agent run "<command>"``        → jalankan shell command via safety policy
- ``ai-agent project list``           → daftar project terdaftar
- ``ai-agent project use <name>``     → switch project aktif (per chat CLI = chat_id 0)
- ``ai-agent context show``           → ringkasan context (project + env)
- ``ai-agent tasks list``             → daftar tasks (placeholder, lihat catatan)

Output default human-readable; ``--json`` switch ke JSON terstruktur.
Exit code = 0 kalau sukses, non-zero kalau error.

Wiring use case lewat ``composition.build_use_case()`` — TIDAK ada duplikasi DI.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import BASE_DIR, settings
from app.domain.messaging import ChatEvent, ChatEventType, MessageContext
from app.memory.store import ProjectStore
from app.safety.policy import validate_args

# CLI dipakai oleh satu operator lokal — pakai chat_id 0 sebagai sentinel
# supaya ProjectStore yang sama dengan Telegram tetap berlaku.
_CLI_CHAT_ID = 0
_CLI_USER_ID = "__cli__"


@dataclass(frozen=True)
class CLIResult:
    """Hasil eksekusi satu subcommand — dipakai untuk render + exit code."""

    exit_code: int
    human: str
    data: dict[str, Any]


def _project_store() -> ProjectStore:
    return ProjectStore(BASE_DIR / "data")


def _build_context(project_name_override: str | None = None) -> MessageContext:
    store = _project_store()
    if project_name_override:
        proj = store.get_project(project_name_override)
        if proj is None:
            proj = store.get_active_project(_CLI_CHAT_ID, settings.project_dir)
    else:
        proj = store.get_active_project(_CLI_CHAT_ID, settings.project_dir)

    return MessageContext(
        user_id=_CLI_USER_ID,
        conversation_id=str(_CLI_CHAT_ID),
        project_id=proj.id,
        project_root=Path(proj.root_path).expanduser(),
        project_name=proj.name,
    )


# ── Subcommands ──────────────────────────────────────────────────────────────


def _cmd_status() -> CLIResult:
    ctx = _build_context()
    data = {
        "project_id": ctx.project_id,
        "project_name": ctx.project_name,
        "project_root": str(ctx.project_root),
        "ai_provider": settings.ai_provider_default,
        "rag_enabled": settings.rag_enabled,
    }
    human = (
        f"Project: {ctx.project_name} ({ctx.project_id})\n"
        f"Root: {ctx.project_root}\n"
        f"AI provider: {settings.ai_provider_default} (BYOK)\n"
        f"RAG: {'on' if settings.rag_enabled else 'off'}"
    )
    return CLIResult(exit_code=0, human=human, data=data)


def _cmd_ask(text: str) -> CLIResult:
    text = text.strip()
    if not text:
        return CLIResult(
            exit_code=2,
            human="error: ask membutuhkan teks non-empty",
            data={"error": "empty text"},
        )

    from app.composition import build_use_case

    use_case = build_use_case()
    ctx = _build_context()

    events: list[ChatEvent] = list(use_case.handle(text, ctx))
    return _render_events(events)


def _cmd_run(command_text: str) -> CLIResult:
    command_text = command_text.strip()
    if not command_text:
        return CLIResult(
            exit_code=2,
            human="error: run membutuhkan command non-empty",
            data={"error": "empty command"},
        )

    try:
        parts = shlex.split(command_text)
    except ValueError as exc:
        return CLIResult(
            exit_code=2,
            human=f"error: command tidak valid: {exc}",
            data={"error": str(exc)},
        )

    allowed, reason = validate_args(parts)
    if not allowed:
        return CLIResult(
            exit_code=3,
            human=f"ditolak safety policy: {reason}",
            data={"error": reason, "command": parts},
        )

    from app.handlers.process_runners import run_terminal_process

    output = run_terminal_process(parts)
    return CLIResult(
        exit_code=0,
        human=output,
        data={"command": parts, "output": output},
    )


def _cmd_project_list() -> CLIResult:
    store = _project_store()
    active_id = store.get_active_project_id(_CLI_CHAT_ID)
    projects = store.list_projects()

    if not projects:
        return CLIResult(
            exit_code=0,
            human="(belum ada project terdaftar)",
            data={"active_id": active_id, "projects": []},
        )

    lines = ["Daftar project:"]
    items: list[dict[str, Any]] = []
    for p in projects:
        marker = " *" if p.id == active_id else ""
        lines.append(f"- {p.name} ({p.id}){marker}  →  {p.root_path}")
        items.append({
            "id": p.id,
            "name": p.name,
            "root_path": p.root_path,
            "active": p.id == active_id,
        })
    lines.append("\n* = aktif saat ini")
    return CLIResult(
        exit_code=0,
        human="\n".join(lines),
        data={"active_id": active_id, "projects": items},
    )


def _cmd_project_use(name: str) -> CLIResult:
    store = _project_store()
    proj = store.get_project(name)
    if proj is None:
        return CLIResult(
            exit_code=4,
            human=f"Project '{name}' tidak ditemukan. Lihat 'ai-agent project list'.",
            data={"error": "not_found", "name": name},
        )
    store.set_active_project(_CLI_CHAT_ID, proj.id)
    return CLIResult(
        exit_code=0,
        human=f"Switched ke project: {proj.name}\nPath: {proj.root_path}",
        data={"id": proj.id, "name": proj.name, "root_path": proj.root_path},
    )


def _cmd_context_show() -> CLIResult:
    ctx = _build_context()
    data = {
        "user_id": ctx.user_id,
        "conversation_id": ctx.conversation_id,
        "project_id": ctx.project_id,
        "project_name": ctx.project_name,
        "project_root": str(ctx.project_root),
        "base_dir": str(BASE_DIR),
        "terminal_tools_enabled": settings.enable_terminal_tools,
    }
    human = (
        f"User: {ctx.user_id}\n"
        f"Conversation: {ctx.conversation_id}\n"
        f"Project: {ctx.project_name} ({ctx.project_id})\n"
        f"Root: {ctx.project_root}\n"
        f"Base: {BASE_DIR}\n"
        f"Terminal tools: {'on' if settings.enable_terminal_tools else 'off'}"
    )
    return CLIResult(exit_code=0, human=human, data=data)


def _cmd_tasks_list() -> CLIResult:
    # Placeholder: project belum punya domain "tasks" terstandardisasi.
    # Lihat catatan di commit body untuk follow-up.
    return CLIResult(
        exit_code=0,
        human="(belum ada task store — fitur menunggu desain skill/task model)",
        data={"tasks": [], "note": "not_implemented"},
    )


# ── Event rendering ──────────────────────────────────────────────────────────


def _render_events(events: Iterable[ChatEvent]) -> CLIResult:
    """Reduce stream event jadi satu output + exit code."""
    text_chunks: list[str] = []
    final_text: str | None = None
    last_error: str | None = None
    intent: dict[str, Any] | None = None
    action_results: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []

    for ev in events:
        payloads.append({"type": ev.type.value, "payload": ev.payload})
        if ev.type == ChatEventType.INTENT_CLASSIFIED:
            intent = dict(ev.payload)
        elif ev.type == ChatEventType.TEXT_CHUNK:
            text_chunks.append(str(ev.payload.get("text", "")))
        elif ev.type == ChatEventType.ACTION_RESULT:
            action_results.append({
                "action": ev.payload.get("action"),
                "output": ev.payload.get("output"),
            })
        elif ev.type == ChatEventType.FINAL:
            final_text = str(ev.payload.get("text", ""))
        elif ev.type == ChatEventType.ERROR:
            last_error = str(ev.payload.get("message", ""))

    if last_error is not None:
        return CLIResult(
            exit_code=1,
            human=f"error: {last_error}",
            data={"error": last_error, "events": payloads},
        )

    human = final_text if final_text else "".join(text_chunks)
    if not human:
        human = "(kosong)"

    return CLIResult(
        exit_code=0,
        human=human,
        data={
            "final": final_text,
            "intent": intent,
            "actions": action_results,
            "events": payloads,
        },
    )


# ── Argparse wiring ──────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-agent",
        description="Local CLI for ai-agent orchestrator (same brain as Telegram).",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON instead of human-readable output",
    )

    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("status", help="show project + AI status")

    ask = sub.add_parser("ask", help="send a natural-language message")
    ask.add_argument("text", help="message text (quote if it contains spaces)")

    run_p = sub.add_parser("run", help="run a shell command via safety policy")
    run_p.add_argument("command", help="shell command (quoted)")

    proj = sub.add_parser("project", help="project management")
    proj_sub = proj.add_subparsers(dest="project_command", required=True)
    proj_sub.add_parser("list", help="list known projects")
    use = proj_sub.add_parser("use", help="switch active project")
    use.add_argument("name", help="project id or name")

    context = sub.add_parser("context", help="context inspection")
    context_sub = context.add_subparsers(dest="context_command", required=True)
    context_sub.add_parser("show", help="show current message context")

    tasks = sub.add_parser("tasks", help="task management (placeholder)")
    tasks_sub = tasks.add_subparsers(dest="tasks_command", required=True)
    tasks_sub.add_parser("list", help="list tasks (not yet implemented)")

    return parser


def _dispatch(ns: argparse.Namespace) -> CLIResult:
    if ns.subcommand == "status":
        return _cmd_status()
    if ns.subcommand == "ask":
        return _cmd_ask(ns.text)
    if ns.subcommand == "run":
        return _cmd_run(ns.command)
    if ns.subcommand == "project":
        if ns.project_command == "list":
            return _cmd_project_list()
        if ns.project_command == "use":
            return _cmd_project_use(ns.name)
    if ns.subcommand == "context" and ns.context_command == "show":
        return _cmd_context_show()
    if ns.subcommand == "tasks" and ns.tasks_command == "list":
        return _cmd_tasks_list()
    return CLIResult(exit_code=2, human="unknown command", data={"error": "unknown"})


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)

    try:
        result = _dispatch(ns)
    except Exception as exc:  # CLI boundary: convert any error ke exit code
        if ns.as_json:
            sys.stdout.write(json.dumps({"error": str(exc)}) + "\n")
        else:
            sys.stderr.write(f"error: {exc}\n")
        return 1

    if ns.as_json:
        sys.stdout.write(json.dumps(result.data, ensure_ascii=False) + "\n")
    else:
        stream = sys.stderr if result.exit_code != 0 else sys.stdout
        stream.write(result.human + "\n")
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
