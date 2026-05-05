"""Slash command handlers + parser.

Setiap ``cmd_*`` me-mutate ``_state`` dan/atau cetak ke output area.
``parse_command`` adalah pure function — bisa ditest tanpa I/O.

Semua handler async — dispatch via ``app.create_background_task`` di
``_runner._accept_input``. Cancellation pakai ``asyncio.Task.cancel()``.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from typing import Any

import httpx
from prompt_toolkit.application import run_in_terminal

from app.config import settings
from app.tui import _state
from app.tui._completer import TuiCompleter
from app.tui._http import client, fmt_http_error
from app.tui._output import print_parts, println
from app.tui._session import (
    LoginAbortedError,
    Session,
    clear_session,
    poll_pair_code,
    qr_ascii,
    request_pair_code,
    revoke_session,
    save_session,
    validate_session,
)
from app.tui._statusbar import probe_health, update_status

DOCKER_LOG_CONTAINER = "aiagent_bot"


def parse_command(line: str) -> tuple[str, list[str]] | None:
    """Pure parser — no I/O, easy to test."""
    line = line.strip()
    if not line.startswith("/"):
        return None
    parts = shlex.split(line[1:])
    if not parts:
        return None
    return parts[0].lower(), parts[1:]


async def cmd_help() -> None:
    println("class:section", "  Commands")
    println("class:rule",    "  " + "─" * 52)
    rows = [
        ("/help",                 "tampilkan daftar command ini"),
        ("/login",                "login Google via QR — wajib pertama kali"),
        ("/logout",               "logout session TUI saat ini"),
        ("/me",                   "info user yang sedang login"),
        ("/pair-telegram",        "link bot Telegram ke akun ini via QR"),
        ("/status",               "mode bot, jumlah user, versi backend"),
        ("/users",                "daftar user terdaftar (admin)"),
        ("/admin-logout <email>", "putus link Telegram user (admin)"),
        ("/logs [n]",             "tail n baris log Docker (default 50)"),
        ("/logs -f",              "follow log live  (Ctrl+C untuk stop)"),
        ("/shell",                "drop ke shell  —  exit untuk kembali"),
        ("/clear",                "bersihkan output TUI"),
        ("/quit",                 "keluar dari TUI"),
        ("",                      ""),
        ("(teks bebas)",          "kirim chat ke bot  —  perlu /login dulu"),
    ]
    for cmd, desc in rows:
        if not cmd and not desc:
            println("", "")
            continue
        print_parts([
            ("class:cmd.name", f"  {cmd:<26}"),
            ("class:cmd.desc", desc),
        ])
    println("", "")


async def cmd_status() -> None:
    println("class:section", "  Backend Status")
    println("class:rule",    "  " + "─" * 52)
    reachable, info = await probe_health()
    if reachable:
        println("class:ok",  f"  ✓  online    {settings.app_url}  mode={info}")
    else:
        println("class:err", f"  ✗  offline   {settings.app_url}  ({info})")
        return
    try:
        async with client() as c:
            r = await c.get("/admin/status")
        if r.status_code == 200:
            data = r.json()
            println("", f"  ·  mode      {data.get('mode', '-')}")
            println("", f"  ·  users     {data.get('user_count', 0)}")
            println("", f"  ·  version   {data.get('version', '-')}")
        else:
            println("class:dim", f"  /admin/status: HTTP {r.status_code} {r.text[:100]}")
    except httpx.HTTPError as exc:
        println("class:err", f"  /admin/status: {fmt_http_error(exc)}")
    println("", "")


async def cmd_users(completer: TuiCompleter) -> None:
    try:
        async with client() as c:
            r = await c.get("/admin/users")
    except httpx.HTTPError as exc:
        println("class:err", f"  request gagal: {fmt_http_error(exc)}")
        return
    if r.status_code != 200:
        println("class:err", f"  HTTP {r.status_code}: {r.text[:200]}")
        return
    payload: dict[str, Any] = r.json()
    users = payload.get("users", [])
    if not users:
        println("class:dim", "  belum ada user terdaftar.")
        return
    emails: list[str] = []
    println("class:section", "  Users")
    println("class:rule",    "  " + "─" * 52)
    print_parts([
        ("class:table.hdr", f"  {'email':<35}{'name':<25}{'telegram':<20}"),
        ("class:table.hdr", "created"),
    ])
    println("class:rule", "  " + "─" * 52)
    for u in users:
        email = u.get("email") or "-"
        name = u.get("display_name") or "-"
        tg_links = [
            f"@{a['username']}" if a.get("username") else str(a.get("telegram_user_id"))
            for a in u.get("telegram_accounts", [])
        ]
        tg = ", ".join(tg_links) if tg_links else "-"
        created = (u.get("created_at") or "")[:19]
        print_parts([
            ("class:user.email", f"  {email:<35}"),
            ("",                 f"{name:<25}"),
            ("class:dim",        f"{tg:<20}"),
            ("class:dim",        created),
        ])
        if u.get("email"):
            emails.append(u["email"])
    println("", "")
    completer.set_emails(emails)


async def cmd_login() -> None:
    """Trigger Google OAuth login flow + render QR + poll session token.

    Setiap /login mencancel task /login lama (kalau ada) lewat
    ``Task.cancel()``. Task lama keluar via ``asyncio.CancelledError``
    tanpa nyampah ke layar attempt baru.
    """
    if _state.active_session is not None:
        println(
            "class:dim",
            f"  sudah login sebagai {_state.active_session.email}. /logout dulu kalau mau ganti.",
        )
        return

    prev = _state.login_task
    if prev is not None and not prev.done():
        prev.cancel()
    _state.login_task = asyncio.current_task()

    try:
        try:
            code, login_url = await request_pair_code()
        except Exception as exc:
            println("class:err", f"  gagal minta pair code: {exc}")
            return

        is_local = any(host in settings.app_url for host in ("localhost", "127.0.0.1"))
        browser_opened = False
        if is_local:
            try:
                import webbrowser
                browser_opened = webbrowser.open(login_url, new=2, autoraise=True)
            except Exception:
                browser_opened = False

        println("", "")
        println("class:section", "  Login Google")
        println("class:rule",    "  " + "─" * 52)
        print_parts([
            ("class:cmd.name", "  Pair code:  "),
            ("class:ok", code),
        ])
        println("", "")

        println("class:cmd.name", "  Opsi 1 · Browser")
        print_parts([
            ("class:dim", "    "),
            ("class:link", login_url),
        ])
        if is_local:
            if browser_opened:
                println("class:ok",  "    ↳ browser auto-dibuka di komputer ini.")
            else:
                println("class:dim", "    ↳ buka URL di atas secara manual.")
        else:
            println("class:dim", "    buka URL di atas dari komputer manapun.")

        println("", "")
        println("class:cmd.name", "  Opsi 2 · Scan QR dari HP")
        for line in qr_ascii(login_url).splitlines():
            println("", f"    {line}")
        println("", "")
        println("class:dim", "  menunggu konfirmasi… (Ctrl-C untuk batal)")

        deadline = asyncio.get_event_loop().time() + 600.0
        token: str | None = None
        while asyncio.get_event_loop().time() < deadline and _state.running[0]:
            try:
                token = await poll_pair_code(code)
            except LoginAbortedError as exc:
                println("class:err", f"  login dibatalkan: {exc}")
                return
            if token:
                break
            await asyncio.sleep(2.0)

        if not token:
            println("class:warn", "  timeout — login tidak selesai dalam 10 menit.")
            return

        session, reason = await validate_session(token)
        if session is None:
            println("class:err", f"  validate /auth/me gagal: {reason}")
            println("class:dim", "  token tetap disimpan; coba /me nanti untuk refresh.")
            session = Session(
                token=token,
                user_id="",
                email="",
                display_name=None,
                backend_url=settings.app_url,
            )

        save_session(session)
        _state.active_session = session
        label = session.email or "(belum lengkap — coba /me)"
        println("class:ok", f"  ✓ login tersimpan sebagai {label}")
        await update_status()
    except asyncio.CancelledError:
        # /login baru sudah ambil alih — exit silent.
        return
    finally:
        if _state.login_task is asyncio.current_task():
            _state.login_task = None


async def cmd_logout_session() -> None:
    """Logout session TUI saat ini (non-args /logout)."""
    session = _state.active_session
    if session is None:
        println("class:dim", "  belum login.")
        return
    revoked = await revoke_session(session.token)
    clear_session()
    _state.active_session = None
    if revoked:
        println("class:ok", "  ✓ logged out (session di backend di-revoke)")
    else:
        println(
            "class:warn",
            "  session lokal dihapus, backend tidak respons. Token mungkin masih hidup.",
        )
    await update_status()


async def cmd_me() -> None:
    session = _state.active_session
    if session is None:
        println("class:dim", "  belum login. Ketik /login.")
        return
    println("class:ai", f"  email   : {session.email}")
    if session.display_name:
        println("class:ai", f"  name    : {session.display_name}")
    println("class:dim", f"  user_id : {session.user_id}")
    println("class:dim", f"  backend : {session.backend_url}")


async def cmd_pair_telegram() -> None:
    """Inisiasi Telegram pair: minta code → render QR ke deep link bot."""
    session = _state.active_session
    if session is None:
        println("class:warn", "  login dulu via /login sebelum pair Telegram.")
        return

    try:
        # Cold-start backend bisa ~4-5 detik (DB session lookup + Telegram
        # getMe untuk bot username). Warm call ~1.5s.
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as c:
            r = await c.post(
                f"{settings.app_url}/auth/telegram/pair-init",
                headers={"Authorization": f"Bearer {session.token}"},
            )
    except httpx.HTTPError as exc:
        println("class:err", f"  request gagal: {fmt_http_error(exc)}")
        return

    if r.status_code != 200:
        println("class:err", f"  HTTP {r.status_code}: {r.text[:200]}")
        return

    data = r.json()
    code = data["code"]
    deep_link = data["deep_link"]
    expires_in = data.get("expires_in_sec", 600)

    println("", "")
    println("class:section", "  Pair Telegram")
    println("class:rule",    "  " + "─" * 52)
    print_parts([
        ("class:cmd.name", "  Pair code:  "),
        ("class:ok", code),
    ])
    println("", "")

    println("class:cmd.name", "  Opsi 1 · Buka link (Telegram Desktop / mobile)")
    print_parts([
        ("class:dim", "    "),
        ("class:link", deep_link),
    ])
    println(
        "class:dim",
        "    ↳ kalau Telegram Desktop terinstall, klik link akan auto-buka bot.",
    )

    println("", "")
    println("class:cmd.name", "  Opsi 2 · Scan QR dari HP")
    for line in qr_ascii(deep_link).splitlines():
        println("", f"    {line}")
    println("", "")
    println(
        "class:dim",
        f"  code berlaku {expires_in // 60} menit. "
        "Setelah scan/klik, bot reply 'Berhasil terhubung'.",
    )


async def cmd_admin_logout(args: list[str]) -> None:
    """Admin operation: putus link Telegram & device milik user X."""
    if not args:
        println("class:warn", "  usage: /admin-logout <email>")
        return
    email = args[0].strip()
    try:
        async with client() as c:
            r = await c.post(f"/admin/logout/{email}")
    except httpx.HTTPError as exc:
        println("class:err", f"  request gagal: {fmt_http_error(exc)}")
        return
    if r.status_code == 200:
        data = r.json()
        println(
            "class:ok",
            f"  admin-logout {email}: hapus {data.get('removed_telegram', 0)} link Telegram "
            f"& {data.get('removed_devices', 0)} device.",
        )
    elif r.status_code == 404:
        println("class:dim", f"  user {email} tidak ditemukan.")
    else:
        println("class:err", f"  HTTP {r.status_code}: {r.text[:200]}")


async def cmd_logs(args: list[str]) -> None:
    follow = "-f" in args
    tail_args = [a for a in args if a != "-f"]
    n = int(tail_args[0]) if tail_args and tail_args[0].isdigit() else 50

    docker_cmd = ["docker", "logs", "--tail", str(n)]
    if follow:
        docker_cmd.append("-f")
    docker_cmd.append(DOCKER_LOG_CONTAINER)

    if follow:
        # Follow path: pakai run_in_terminal supaya output langsung ke
        # terminal user (suspend TUI dulu). Subprocess di dalamnya tetap
        # blocking sync — itu desain prompt_toolkit.
        def _follow_fn() -> None:
            print("--- following log (Ctrl+C untuk stop) ---")
            try:
                proc = subprocess.Popen(
                    docker_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                try:
                    for line in iter(proc.stdout.readline, ""):  # type: ignore[union-attr]
                        print(f"  {line.rstrip()}")
                except KeyboardInterrupt:
                    proc.kill()
                    print("\n--- stopped ---")
            except FileNotFoundError:
                print("  docker tidak ditemukan di PATH.")
        await run_in_terminal(_follow_fn)
        return

    # Tail path: async subprocess, hasil dirender ke output area TUI.
    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        println("class:dim", "  docker tidak ditemukan di PATH.")
        return

    try:
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        println("class:warn", "  docker logs timeout (10s).")
        return

    if proc.returncode != 0:
        msg = stdout_bytes.decode("utf-8", errors="replace").strip()[:200]
        println("class:warn", f"  docker logs gagal: {msg}")
        return
    lines_out = stdout_bytes.decode("utf-8", errors="replace").splitlines()
    if not lines_out:
        println("class:dim", "  log kosong.")
        return
    for line in lines_out:
        println("class:dim", f"  {line}")


async def cmd_shell() -> None:
    shell = os.environ.get("SHELL") or "/bin/zsh"

    def _shell_fn() -> None:
        print(f"  drop ke {shell} — ketik 'exit' untuk kembali ke TUI.")
        print()
        subprocess.run([shell], check=False)
        print()
        print("  kembali ke TUI.")

    await run_in_terminal(_shell_fn)
