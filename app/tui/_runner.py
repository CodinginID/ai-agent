"""Entry point: build layout, key bindings, style → run Application."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import Float, FloatContainer, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame

from app.config import BASE_DIR
from app.tui import _state
from app.tui._chat import send_chat
from app.tui._commands import (
    cmd_admin_logout,
    cmd_help,
    cmd_login,
    cmd_logout_session,
    cmd_logs,
    cmd_me,
    cmd_pair_telegram,
    cmd_shell,
    cmd_status,
    cmd_users,
    parse_command,
)
from app.tui._completer import TuiCompleter
from app.tui._http import fetch_emails
from app.tui._output import (
    clear_output,
    get_output_cursor,
    get_output_text,
    print_parts,
    println,
)
from app.tui._statusbar import (
    get_status_bar_text,
    status_loop,
    update_status,
)
from app.tui._session import clear_session, load_session, validate_session

_HISTORY_FILE: Path = BASE_DIR / "data" / ".tui_history"

# ── logo (ANSI Shadow block art, OCTOPUS, 6-line gradient) ───────────────────
# Each row is coloured separately to create a top→bottom cyan-to-purple sweep.
# Columns: O(9) C(8) T(9) O(9) P(8) U(9) S(8)  total 60 + 6 sep + 2 indent = 68 chars
_LOGO: list[tuple[str, str]] = [
    ("class:logo.l1", "   ██████╗   ██████╗ ████████╗  ██████╗  ██████╗  ██╗   ██╗ ███████╗\n"),
    ("class:logo.l2", "  ██╔═══██╗ ██╔════╝ ╚══██╔══╝ ██╔═══██╗ ██╔══██╗ ██║   ██║ ██╔════╝\n"),
    ("class:logo.l3", "  ██║   ██║ ██║         ██║    ██║   ██║ ██████╔╝ ██║   ██║ ███████╗\n"),
    ("class:logo.l4", "  ██║   ██║ ██║         ██║    ██║   ██║ ██╔═══╝  ██║   ██║ ╚════██║\n"),
    ("class:logo.l5", "  ╚██████╔╝ ╚██████╗    ██║    ╚██████╔╝ ██║      ╚██████╔╝ ███████║\n"),
    ("class:logo.l6", "   ╚═════╝   ╚═════╝    ╚═╝     ╚═════╝  ╚═╝       ╚═════╝  ╚══════╝\n"),
    ("class:logo.sub",      "  OCTOPUS  ·  Server Monitoring  ·  Control  ·  AI Chat"),
    ("class:logo.ver",      "  ─────  v0.1.0\n"),
    ("class:logo.hint.key", "  Tab "),
    ("class:logo.hint",     "complete   "),
    ("class:logo.hint.key", "↑↓ "),
    ("class:logo.hint",     "history   "),
    ("class:logo.hint.key", "/help "),
    ("class:logo.hint",     "commands   "),
    ("class:logo.hint.key", "Ctrl-C "),
    ("class:logo.hint",     "quit"),
]


def _build_style() -> Style:
    return Style.from_dict({
        # ── header / logo — vertical cyan→purple gradient ─────────────────────
        "header":             "bg:#0a0f1e",
        "logo.l1":            "bold #06b6d4",   # cyan
        "logo.l2":            "bold #0ea5e9",   # sky
        "logo.l3":            "bold #3b82f6",   # blue
        "logo.l4":            "bold #6366f1",   # indigo
        "logo.l5":            "bold #8b5cf6",   # violet
        "logo.l6":            "#6d28d9",        # deep purple (shadow row, dimmer)
        "logo.sub":           "#475569",
        "logo.ver":           "#0891b2",
        "logo.hint":          "#2d3f55",
        "logo.hint.key":      "bold #3d5473",
        # ── separator line ────────────────────────────────
        "separator":          "#1a2640",
        # ── output area ───────────────────────────────────
        "output":             "bg:#0a0f1e #c8d3e0",
        # ── status bar ────────────────────────────────────
        "statusbar":          "bg:#0f1c30",
        "status.ok":          "bg:#0f1c30 #34d399",
        "status.err":         "bg:#0f1c30 #f87171",
        "status.warn":        "bg:#0f1c30 #fbbf24",
        "status.dim":         "bg:#0f1c30 #4a6080",
        "status.user":        "bg:#0f1c30 bold #60a5fa",
        "status.sep":         "bg:#0f1c30 #1e3350",
        # ── input frame ───────────────────────────────────
        "input.frame":        "bg:#0a0f1e",
        "frame.border":       "#1e3350",
        "input.prefix":       "bold #06b6d4",
        # ── echoed command ────────────────────────────────
        "echo.prompt":        "bold #06b6d4",
        "echo.text":          "#94a3b8",
        # ── output: section / table ───────────────────────
        "section":            "bold #e2e8f0",
        "rule":               "#1e3350",
        "table.hdr":          "bold #4a6080",
        # ── output: status ────────────────────────────────
        "ok":                 "#34d399",
        "err":                "#f87171",
        "warn":               "#fbbf24",
        "dim":                "#4a6080",
        "link":               "#60a5fa underline",
        "ai":                 "#e2e8f0",
        # ── output: commands / users ──────────────────────
        "cmd.name":           "bold #38bdf8",
        "cmd.desc":           "#64748b",
        "user.email":         "#60a5fa",
        # ── completion menu ───────────────────────────────
        "completion-menu.completion":         "bg:#0f1c30 #94a3b8",
        "completion-menu.completion.current": "bg:#0284c7 #ffffff",
        "scrollbar.background":               "bg:#0f1c30",
        "scrollbar.button":                   "bg:#1e3350",
    })


def _build_layout(input_buffer: Buffer) -> Layout:
    header = Window(
        content=FormattedTextControl(text=FormattedText(_LOGO)),
        height=8,
        dont_extend_height=True,
        style="class:header",
    )

    separator = Window(
        height=1,
        char="─",
        dont_extend_height=True,
        style="class:separator",
    )

    output_window = Window(
        content=FormattedTextControl(
            text=get_output_text,
            get_cursor_position=get_output_cursor,
            focusable=False,
        ),
        wrap_lines=True,
        style="class:output",
    )

    status_bar = Window(
        content=FormattedTextControl(text=get_status_bar_text),
        height=1,
        dont_extend_height=True,
        style="class:statusbar",
    )

    input_frame = Frame(
        Window(
            content=BufferControl(
                buffer=input_buffer,
                input_processors=[BeforeInput("> ", style="class:input.prefix")],
                include_default_input_processors=True,
            ),
            height=1,
            dont_extend_height=True,
        ),
        style="class:input.frame",
    )

    return Layout(
        FloatContainer(
            content=HSplit([header, separator, output_window, status_bar, input_frame]),
            floats=[Float(xcursor=True, ycursor=True, content=CompletionsMenu(max_height=8))],
        ),
        focused_element=input_buffer,
    )


def _build_key_bindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("c-c")
    @kb.add("c-d")
    def _on_exit(event: Any) -> None:
        _state.running[0] = False
        event.app.exit()

    # Application custom (bukan PromptSession) tidak auto-bind Enter ke
    # validate_and_handle. Pakai eager=True supaya default Enter binding
    # tidak ikut fire (mencegah dispatch ganda → poll_pair_code dua kali →
    # backend kasih 410 di poll kedua karena code sudah dikonsumsi).
    @kb.add("enter", eager=True)
    def _on_enter(event: Any) -> None:
        event.current_buffer.validate_and_handle()

    return kb


def run() -> None:
    _state.running[0] = True
    _state.output.clear()

    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    completer = TuiCompleter()

    input_buffer = Buffer(
        completer=completer,
        history=FileHistory(str(_HISTORY_FILE)),
        complete_while_typing=True,
        name="input",
    )

    def _accept_input(buff: Buffer) -> None:
        text = buff.text.strip()
        buff.reset()
        if not text:
            return

        print_parts([("class:echo.prompt", "  > "), ("class:echo.text", text)])
        parsed = parse_command(text)

        # Sync fast-paths: commands tanpa I/O atau yang harus jalan di
        # event-loop thread tanpa menunggu await chain.
        if parsed:
            cmd, _args_fp = parsed
            if cmd in ("quit", "exit", "q"):
                _state.running[0] = False
                if _state.app is not None:
                    _state.app.exit()
                return
            if cmd == "clear":
                clear_output()
                return

        # Sisanya: schedule sebagai background task. prompt_toolkit akan
        # cancel task yang masih jalan saat app exit.
        if _state.app is not None:
            _state.app.create_background_task(_dispatch(parsed, text, completer))

    input_buffer.accept_handler = _accept_input

    _state.app = Application(
        layout=_build_layout(input_buffer),
        key_bindings=_build_key_bindings(),
        style=_build_style(),
        full_screen=True,
        mouse_support=False,
    )

    println("class:dim", "  Ketik /help untuk daftar command, atau langsung kirim pesan ke bot.")
    println("", "")

    async def _init() -> None:
        await update_status()

        # Try restore session dari ~/.config/ai-agent/session.json.
        stored = load_session()
        if stored is not None:
            validated, reason = await validate_session(stored.token)
            if validated is not None:
                _state.active_session = validated
                println("class:dim", f"  ✓ session pulih sebagai {validated.email}")
            else:
                clear_session()
                println("class:warn", f"  session lokal invalid ({reason}) — ketik /login.")
        else:
            println("class:warn", "  belum login — ketik /login untuk mulai.")

        if _state.app is not None:
            _state.app.invalidate()
        completer.set_emails(await fetch_emails())

    async def _async_run() -> None:
        # ``create_background_task`` butuh event loop yang sudah running, jadi
        # schedule task setelah masuk async context.
        assert _state.app is not None
        _state.app.create_background_task(_init())
        _state.app.create_background_task(status_loop())
        await _state.app.run_async()

    import asyncio
    try:
        asyncio.run(_async_run())
    finally:
        _state.running[0] = False

    print("  Bye.")


async def _dispatch(
    parsed: tuple[str, list[str]] | None,
    text: str,
    completer: TuiCompleter,
) -> None:
    if parsed is None:
        await send_chat(text)
        return
    cmd, args = parsed
    handlers: dict[str, Callable[[], Awaitable[None]]] = {
        "help":           cmd_help,
        "?":              cmd_help,
        "login":          cmd_login,
        "logout":         (
            cmd_logout_session if not args
            else lambda: cmd_admin_logout(args)  # backwards compat: /logout <email>
        ),
        "me":             cmd_me,
        "pair-telegram":  cmd_pair_telegram,
        "pair":           cmd_pair_telegram,
        "status":         cmd_status,
        "users":          lambda: cmd_users(completer),
        "admin-logout":   lambda: cmd_admin_logout(args),
        "logs":           lambda: cmd_logs(args),
        "shell":          cmd_shell,
        "zsh":            cmd_shell,
    }
    handler = handlers.get(cmd)
    if handler is None:
        println("class:dim", f"  command tidak dikenal: /{cmd}")
    else:
        await handler()
