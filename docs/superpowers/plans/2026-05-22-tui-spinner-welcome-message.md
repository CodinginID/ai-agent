# TUI Spinner + Welcome Message Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tampilkan spinner animasi di output area TUI saat menunggu respons AI, dan perkuat persona Octopus di chat prompt supaya greeting terasa natural bukan generik.

**Architecture:** Spinner menggunakan flag `spinner_active` di `_state.py` sebagai single source of truth. Background loop permanen di `_runner.py` menganimasikan frame tiap 80ms ke `_state.spinner_line`, yang di-render oleh `get_output_text()` sebagai baris terakhir output. `send_chat()` set/clear flag; `render_sse()` clear flag saat event pertama tiba. Welcome message diperbaiki via update `_CHAT_PROMPT_TEMPLATE` di `use_cases.py` — model tetap generate sendiri, tapi instruksi lebih spesifik.

**Tech Stack:** Python 3.13 · prompt_toolkit · httpx SSE · pytest

---

## File Map

| File | Action |
|---|---|
| `app/tui/_state.py` | Modify: tambah `spinner_active: bool` + `spinner_line` |
| `app/tui/_output.py` | Modify: append `spinner_line` di `get_output_text()` |
| `app/tui/_chat.py` | Modify: set/clear spinner di `send_chat()` + hapus `intent_classified` rendering |
| `app/tui/_runner.py` | Modify: start `spinner_loop()` sebagai background task |
| `app/domain/use_cases.py` | Modify: perkuat `_CHAT_PROMPT_TEMPLATE` |
| `tests/tui/__init__.py` | Create: kosong |
| `tests/tui/test_spinner.py` | Create: unit tests spinner state + output rendering |

---

## Task 1: Tambah spinner state ke `_state.py`

**Files:**
- Modify: `app/tui/_state.py`

- [ ] **Step 1: Tulis failing test**

Buat `tests/tui/__init__.py` (kosong) dan `tests/tui/test_spinner.py`:

```python
"""Unit tests TUI spinner state."""
from app.tui import _state


def setup_function() -> None:
    _state.spinner_active = False
    _state.spinner_line = None


def test_spinner_defaults_to_inactive() -> None:
    assert _state.spinner_active is False


def test_spinner_line_defaults_to_none() -> None:
    assert _state.spinner_line is None


def test_spinner_state_can_be_set() -> None:
    _state.spinner_active = True
    _state.spinner_line = ("class:dim", "  ⠹ octopus sedang berpikir...\n")
    assert _state.spinner_active is True
    assert _state.spinner_line is not None
```

- [ ] **Step 2: Jalankan test — harus FAIL**

```bash
cd /Users/anonymous/Documents/office/codinginid/ai-agent
pytest tests/tui/test_spinner.py -v 2>&1 | head -20
```

Expected: `AttributeError: module 'app.tui._state' has no attribute 'spinner_active'`

- [ ] **Step 3: Tambah dua atribut ke `_state.py`**

Ganti isi `app/tui/_state.py` dengan:

```python
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

# Spinner: True saat sedang menunggu respons dari backend.
spinner_active: bool = False
# Baris animasi yang di-render di akhir output saat spinner aktif. None = tidak tampil.
spinner_line: tuple[str, str] | None = None
```

- [ ] **Step 4: Jalankan test — harus PASS**

```bash
pytest tests/tui/test_spinner.py -v
```

Expected: 3 test PASS.

- [ ] **Step 5: Commit**

```bash
git add app/tui/_state.py tests/tui/__init__.py tests/tui/test_spinner.py
git commit -m "feat(tui): add spinner_active + spinner_line state"
```

---

## Task 2: Render spinner di `get_output_text()`

**Files:**
- Modify: `app/tui/_output.py`
- Test: `tests/tui/test_spinner.py`

- [ ] **Step 1: Tambah test untuk get_output_text dengan spinner**

Append ke `tests/tui/test_spinner.py`:

```python
from app.tui._output import get_output_text


def test_get_output_text_includes_spinner_when_active() -> None:
    _state.output.clear()
    _state.output.append(("class:ai", "respons sebelumnya\n"))
    _state.spinner_line = ("class:dim", "  ⠹ octopus sedang berpikir...\n")

    result = get_output_text()
    texts = [text for _, text in result]
    assert "respons sebelumnya\n" in texts
    assert "  ⠹ octopus sedang berpikir...\n" in texts
    # Spinner harus di akhir
    assert texts[-1] == "  ⠹ octopus sedang berpikir...\n"


def test_get_output_text_no_spinner_when_none() -> None:
    _state.output.clear()
    _state.output.append(("class:ai", "teks\n"))
    _state.spinner_line = None

    result = get_output_text()
    texts = [text for _, text in result]
    assert len(texts) == 1
    assert texts[0] == "teks\n"
```

- [ ] **Step 2: Jalankan test — harus FAIL**

```bash
pytest tests/tui/test_spinner.py::test_get_output_text_includes_spinner_when_active -v
```

Expected: FAIL — spinner tidak muncul di output.

- [ ] **Step 3: Update `get_output_text()` di `_output.py`**

Ganti fungsi `get_output_text` (baris 34-35):

```python
def get_output_text() -> FormattedText:
    parts = list(_state.output)
    if _state.spinner_line is not None:
        parts.append(_state.spinner_line)
    return FormattedText(parts)
```

- [ ] **Step 4: Jalankan test — harus PASS**

```bash
pytest tests/tui/test_spinner.py -v
```

Expected: semua test PASS.

- [ ] **Step 5: Commit**

```bash
git add app/tui/_output.py tests/tui/test_spinner.py
git commit -m "feat(tui): render spinner_line di akhir output area"
```

---

## Task 3: Spinner loop — animasi background

**Files:**
- Modify: `app/tui/_runner.py`

Spinner loop adalah coroutine permanen yang berjalan selama TUI aktif. Ia menganimasikan frame tiap 80ms selama `spinner_active` True, dan clear `spinner_line` saat tidak aktif.

- [ ] **Step 1: Tambah `spinner_loop()` dan start di `_async_run()`**

Di `app/tui/_runner.py`, tambah import di bagian atas (setelah import `status_loop`):

```python
from app.tui._output import spinner_loop
```

Lalu buat fungsi `spinner_loop` di `app/tui/_output.py` (append setelah `get_output_cursor`):

```python
_SPINNER_FRAMES: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


async def spinner_loop() -> None:
    """Background coroutine: animasi spinner saat _state.spinner_active == True."""
    import asyncio

    frame_idx = 0
    while _state.running[0]:
        if _state.spinner_active:
            frame = _SPINNER_FRAMES[frame_idx % len(_SPINNER_FRAMES)]
            _state.spinner_line = ("class:dim", f"  {frame} octopus sedang berpikir...\n")
            frame_idx += 1
            if _state.app is not None:
                _state.app.invalidate()
            try:
                await asyncio.sleep(0.08)
            except asyncio.CancelledError:
                return
        else:
            if _state.spinner_line is not None:
                _state.spinner_line = None
                frame_idx = 0
                if _state.app is not None:
                    _state.app.invalidate()
            try:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                return
```

- [ ] **Step 2: Start `spinner_loop()` di `_async_run()` di `_runner.py`**

Di `_runner.py`, update import di atas (cari baris `from app.tui._statusbar import`):

```python
from app.tui._output import (
    clear_output,
    get_output_cursor,
    get_output_text,
    print_parts,
    println,
    spinner_loop,
)
```

Di dalam `_async_run()` (setelah `_state.app.create_background_task(status_loop())`), tambah:

```python
_state.app.create_background_task(spinner_loop())
```

Sehingga blok `_async_run` menjadi:

```python
async def _async_run() -> None:
    assert _state.app is not None
    _state.app.create_background_task(_init())
    _state.app.create_background_task(status_loop())
    _state.app.create_background_task(spinner_loop())
    from app.tui._worker import run_worker_loop
    _state.app.create_background_task(run_worker_loop())
    await _state.app.run_async()
```

- [ ] **Step 3: Verifikasi tidak ada error import**

```bash
cd /Users/anonymous/Documents/office/codinginid/ai-agent
python -c "from app.tui._output import spinner_loop; print('OK')"
python -c "from app.tui._runner import run; print('OK')"
```

Expected: `OK` di kedua baris.

- [ ] **Step 4: Jalankan full test suite**

```bash
pytest tests/tui/ -v
```

Expected: semua PASS.

- [ ] **Step 5: Commit**

```bash
git add app/tui/_output.py app/tui/_runner.py
git commit -m "feat(tui): add spinner animation background loop"
```

---

## Task 4: Set/clear spinner di `send_chat()` + hapus intent rendering

**Files:**
- Modify: `app/tui/_chat.py`
- Test: `tests/tui/test_spinner.py`

- [ ] **Step 1: Tambah test untuk send_chat spinner behavior**

Append ke `tests/tui/test_spinner.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


async def _fake_sse_lines(events: list[str]):
    for line in events:
        yield line


def test_render_sse_clears_spinner_on_text_chunk() -> None:
    from app.tui._chat import render_sse

    _state.spinner_active = True
    _state.spinner_line = ("class:dim", "  ⠹ octopus sedang berpikir...\n")
    _state.output.clear()
    _state.app = None

    lines = [
        "event: text_chunk",
        'data: {"text": "Halo!"}',
        "",
        "event: final",
        'data: {"text": ""}',
        "",
    ]

    asyncio.run(render_sse(_fake_sse_lines(lines)))

    assert _state.spinner_active is False


def test_render_sse_clears_spinner_on_error() -> None:
    from app.tui._chat import render_sse

    _state.spinner_active = True
    _state.output.clear()
    _state.app = None

    lines = [
        "event: error",
        'data: {"message": "something failed"}',
        "",
    ]

    asyncio.run(render_sse(_fake_sse_lines(lines)))

    assert _state.spinner_active is False


def test_render_sse_does_not_print_intent_classified() -> None:
    from app.tui._chat import render_sse

    _state.output.clear()
    _state.spinner_active = False
    _state.app = None

    lines = [
        "event: intent_classified",
        'data: {"intent": "chat", "confidence": 0.95}',
        "",
        "event: final",
        'data: {"text": "halo"}',
        "",
    ]

    asyncio.run(render_sse(_fake_sse_lines(lines)))

    texts = [t for _, t in _state.output]
    assert not any("intent" in t for t in texts)
```

- [ ] **Step 2: Jalankan test — harus FAIL**

```bash
pytest tests/tui/test_spinner.py::test_render_sse_clears_spinner_on_text_chunk \
       tests/tui/test_spinner.py::test_render_sse_does_not_print_intent_classified -v
```

Expected: FAIL — spinner tidak ter-clear, intent masih di-print.

- [ ] **Step 3: Update `_chat.py`**

Ganti isi `app/tui/_chat.py` dengan:

```python
"""Chat free-text → POST /chat/send (SSE) → render ke output area."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.tui import _state
from app.tui._http import CHAT_TIMEOUT_SEC, fmt_http_error
from app.tui._output import println


def _clear_spinner() -> None:
    _state.spinner_active = False


async def render_sse(lines: AsyncIterator[str]) -> None:
    event = ""
    data_lines: list[str] = []
    chat_started = False

    def flush() -> None:
        nonlocal chat_started
        if not event:
            return
        try:
            payload = json.loads("\n".join(data_lines)) if data_lines else {}
        except json.JSONDecodeError:
            payload = {}

        if event == "intent_classified":
            pass  # tidak ditampilkan ke user
        elif event == "thinking":
            _clear_spinner()
            println("class:dim", f"  > {payload.get('message', '')}")
        elif event == "approval_required":
            _clear_spinner()
            println("class:warn", f"  butuh approval — plan_id={payload.get('plan_id')}")
            println("", payload.get("summary", ""))
        elif event == "action_started":
            _clear_spinner()
            println("class:dim", f"  > menjalankan {payload.get('action')}...")
        elif event == "action_result":
            println("", payload.get("output", ""))
        elif event == "text_chunk":
            _clear_spinner()
            chunk = payload.get("text", "")
            if not chat_started:
                _state.output.append(("class:ai", "  "))
                chat_started = True
            _state.output.append(("class:ai", chunk))
            if _state.app is not None:
                _state.app.invalidate()
        elif event == "final":
            _clear_spinner()
            if chat_started:
                _state.output.append(("", "\n"))
                if _state.app is not None:
                    _state.app.invalidate()
                chat_started = False
            else:
                final_text = payload.get("text", "")
                if final_text:
                    println("class:ai", f"  {final_text}")
        elif event == "error":
            _clear_spinner()
            if chat_started:
                _state.output.append(("", "\n"))
                chat_started = False
            println("class:err", f"  error: {payload.get('message', '')}")

    async for raw in lines:
        if raw == "":
            flush()
            event = ""
            data_lines = []
            continue
        if raw.startswith("event: "):
            event = raw[len("event: "):].strip()
        elif raw.startswith("data: "):
            data_lines.append(raw[len("data: "):])
    flush()


async def send_chat(text: str) -> None:
    session = _state.active_session
    if session is None:
        println("class:warn", "  belum login. Ketik /login dulu.")
        return
    headers = {
        "Authorization": f"Bearer {session.token}",
        "User-Agent": "octopus-tui/0.1.0",
        "Accept": "text/event-stream",
    }
    _state.spinner_active = True
    try:
        async with httpx.AsyncClient(
            base_url=settings.app_url,
            timeout=httpx.Timeout(CHAT_TIMEOUT_SEC, connect=5.0),
            headers=headers,
            trust_env=False,
        ) as c, c.stream("POST", "/chat/send", json={"text": text}) as resp:
            if resp.status_code == 401:
                _state.spinner_active = False
                println("class:err", "  sesi habis. Ketik /login lagi.")
                return
            if resp.status_code != 200:
                _state.spinner_active = False
                body_bytes = await resp.aread()
                body = body_bytes.decode("utf-8", errors="replace")
                println("class:err", f"  HTTP {resp.status_code}: {body[:200]}")
                return
            await render_sse(resp.aiter_lines())
    except httpx.HTTPError as exc:
        _state.spinner_active = False
        println("class:err", f"  request gagal: {fmt_http_error(exc)}")
```

- [ ] **Step 4: Jalankan semua test TUI**

```bash
pytest tests/tui/ -v
```

Expected: semua PASS.

- [ ] **Step 5: Commit**

```bash
git add app/tui/_chat.py tests/tui/test_spinner.py
git commit -m "feat(tui): set/clear spinner in send_chat + remove intent_classified from output"
```

---

## Task 5: Perkuat persona di `_CHAT_PROMPT_TEMPLATE`

**Files:**
- Modify: `app/domain/use_cases.py:32-48`

- [ ] **Step 1: Ganti `_CHAT_PROMPT_TEMPLATE`**

Di `app/domain/use_cases.py`, ganti baris 32-48 dengan:

```python
_CHAT_PROMPT_TEMPLATE = (
    "Kamu Octopus — asisten pribadi operator server.\n"
    "Kemampuan konkret: pantau CPU/RAM/disk, manage Docker, jalankan git command, "
    "delegasi coding task ke AI agent (Codex/Claude/GLM).\n"
    "Mode sekarang: chat ringan. Tugas berat di-handle modul lain.\n\n"
    "Aturan:\n"
    "1. Jawab dalam bahasa user. User pakai Indonesia → jawab Indonesia.\n"
    "2. SINGKAT. Maksimal 2-3 kalimat kecuali diminta lebih panjang.\n"
    "3. Ketika disapa ('halo', 'hai', 'hi', dsb.) atau ditanya 'siapa kamu': "
    "perkenalkan diri sebagai Octopus + sebutkan 2-3 kemampuan konkret + tanya mau mulai dari mana. "
    "Contoh: 'Halo! Saya Octopus — bisa pantau server, kelola Docker, dan kirim task ke Codex/Claude. "
    "Mau mulai dari mana?'\n"
    "4. JANGAN klaim sudah eksekusi command — kamu tidak punya akses shell di mode chat.\n"
    "5. Kalau user minta aksi server, arahkan ke bahasa natural: "
    "'cek status server', 'cek ram', 'cek disk', 'status docker', 'git status'.\n"
    "6. Untuk coding (refactor, debug), arahkan ke /codex atau /claude.\n\n"
    "Riwayat chat terakhir:\n{history}\n\n"
    "User: {user_text}\nOctopus:"
)
```

- [ ] **Step 2: Verifikasi format string masih valid**

```bash
python -c "
from app.domain.use_cases import _CHAT_PROMPT_TEMPLATE
result = _CHAT_PROMPT_TEMPLATE.format(history='test', user_text='halo')
assert '{history}' not in result
assert '{user_text}' not in result
assert 'Octopus' in result
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Jalankan full test suite**

```bash
pytest tests/ -x -q
```

Expected: semua PASS.

- [ ] **Step 4: Commit**

```bash
git add app/domain/use_cases.py
git commit -m "feat(domain): perkuat persona Octopus di chat prompt template"
```

---

## Self-Review

**Spec coverage:**
- ✅ Spinner muncul di output area saat menunggu respons
- ✅ Spinner hilang saat event pertama (text_chunk/final/error/thinking/action) tiba
- ✅ Intent classified tidak ditampilkan ke user
- ✅ Welcome message lebih natural via prompt yang lebih kuat
- ✅ Background spinner loop permanen — tidak perlu start/stop manual

**Placeholder scan:** Tidak ada TBD atau TODO.

**Type consistency:**
- `spinner_active: bool` → diset `True`/`False` di `send_chat()` ✅
- `spinner_line: tuple[str, str] | None` → diset di `spinner_loop()`, dibaca di `get_output_text()` ✅
- `_clear_spinner()` dipanggil di setiap event branch di `flush()` ✅
