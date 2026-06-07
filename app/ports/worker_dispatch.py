"""Port untuk delegasi job ke worker (TUI di mesin user).

ExecutionLoop (sinkron) memakai port ini saat memutuskan aksi ``delegate``:
alih-alih menjalankan command di server lokal, ia mengirim prompt ke worker
user yang menjalankan agent CLI ber-LLM berbeda (claude/codex/glm).

Sinkron secara sengaja — ExecutionLoop adalah generator sinkron yang dibungkus
``asyncio.to_thread`` oleh caller. Implementasi konkret (``WorkerDispatchAdapter``)
yang menjembatani ke coroutine ``dispatch_agent_job`` di sisi async.

Hexagonal: domain/executor hanya bergantung pada Protocol ini, bukan pada
``app.interfaces.worker_ws`` langsung.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DispatchResult:
    """Hasil agregat dari satu job delegasi ke worker.

    ``output``  : gabungan seluruh job_chunk (stdout agent), sudah di-strip.
    ``summary`` : ringkasan dari worker saat job_done (mis. "exit 0").
    ``ok``      : True kalau job selesai (job_done), False kalau error/timeout.
    ``error``   : pesan error kalau ``ok`` False; string kosong kalau sukses.
    """

    output: str
    summary: str = ""
    ok: bool = True
    error: str = ""


class WorkerDispatchPort(Protocol):
    def dispatch(self, user_id: str, role: str, prompt: str) -> DispatchResult: ...
