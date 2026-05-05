"""Global mutable state untuk TUI.

Dipisah ke modul sendiri supaya semua sub-modul bisa membaca/menulis lewat
``_state.<attr>`` (akses live via attribute lookup), bukan via ``import name``
yang akan membekukan referensi pada saat import time.

Catatan threading: TUI single-threaded di atas asyncio event loop
prompt_toolkit. Tidak butuh lock — semua mutasi ``output`` terjadi pada loop
yang sama.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

    from prompt_toolkit import Application

    from app.tui._session import Session

app: Application[None] | None = None
output: list[tuple[str, str]] = []
status: dict[str, str] = {"online": "?", "mode": "-", "users": "?"}
running: list[bool] = [True]
active_session: Session | None = None

# Task /login yang masih jalan; saat /login dipicu lagi, task lama di-cancel.
login_task: asyncio.Task[None] | None = None
