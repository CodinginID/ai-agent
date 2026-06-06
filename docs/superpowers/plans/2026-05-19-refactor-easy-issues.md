# Refactor Easy Issues (#15, #16, #18) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Selesaikan tiga issue termudah: tutup #18 (dead code sudah hilang), tambah multi-stage Docker build (#16), dan perbaiki dependency leak di domain layer (#15).

**Architecture:** Issue #18 cukup tutup di GitHub — dead code sudah dihapus. Issue #16 adalah perubahan konfigurasi Docker murni. Issue #15 membutuhkan penambahan dua Protocol baru ke `ports/agents.py` dan dua adapter konkret, sehingga `use_cases.py` bebas dari import adapter.

**Tech Stack:** Python 3.13 · pytest · Docker multi-stage · SQLAlchemy · Redis (asyncio via ThreadPoolExecutor)

---

## File Map

| File | Action |
|---|---|
| `app/ports/agents.py` | Modify: tambah `AgentRoleResolver` + `HandoffContextProvider` Protocol |
| `app/domain/use_cases.py` | Modify: hapus `_agent_for_intent` + `_maybe_prepend_handoff`, inject lewat Protocol |
| `app/adapters/agent_role_resolver.py` | Create: `SqlAgentRoleResolver` implements `AgentRoleResolver` |
| `app/adapters/handoff_context.py` | Create: `RedisHandoffContextProvider` implements `HandoffContextProvider` |
| `app/composition.py` | Modify: inject dua adapter baru ke `build_use_case()` |
| `Dockerfile` | Modify: multi-stage build |
| `.dockerignore` | Modify: tambah entri yang kurang |
| `tests/domain/test_use_cases.py` | Create: unit test `HandleMessageUseCase` agent delegation path |

---

## Task 1: Tutup Issue #18 (Dead Code Sudah Hilang)

**Files:**
- No file changes needed

- [ ] **Step 1: Verifikasi dead code memang sudah tidak ada**

```bash
grep -n "parse_intent_with_ai\|parse_intent_locally\|is_greeting\|looks_like_general_chat" app/bot.py
```

Expected: no output (file hanya 206 baris, clean)

- [ ] **Step 2: Close issue dengan comment**

```bash
gh issue close 18 --repo CodinginID/ai-agent \
  --comment "Dead code sudah tidak ada di bot.py (206 baris sekarang). Resolved saat refactor monolith ke handlers/."
```

---

## Task 2: Multi-Stage Docker Build (#16)

**Files:**
- Modify: `Dockerfile`
- Modify: `.dockerignore`

- [ ] **Step 1: Catat image size sebelum perubahan**

```bash
docker build -t ai-agent:before . 2>&1 | tail -5
docker image inspect ai-agent:before --format '{{.Size}}' | numfmt --to=iec
```

Expected: ukuran tercatat untuk dibandingkan nanti.

- [ ] **Step 2: Tulis Dockerfile multi-stage**

Ganti isi `Dockerfile` dengan:

```dockerfile
# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: production ───────────────────────────────────────────────────────
FROM python:3.13-slim AS production

WORKDIR /app

# git dibutuhkan runtime untuk git_status action
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY app/ ./app/

RUN mkdir -p /app/data

CMD ["python", "-m", "app.main"]
```

- [ ] **Step 3: Update .dockerignore**

Tambahkan entri yang belum ada:

```
.git
.venv
env/
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
.ruff_cache
tests/
docs/
data/
.env
.env.local
!.env.example
*.md
.github/
```

- [ ] **Step 4: Build dan verifikasi**

```bash
docker build -t ai-agent:after .
docker image inspect ai-agent:after --format '{{.Size}}' | numfmt --to=iec
```

Expected: ukuran berkurang ≥ 40% dibanding sebelum. Build harus berhasil tanpa error.

- [ ] **Step 5: Commit**

```bash
git checkout -b refactor/multi-stage-docker
git add Dockerfile .dockerignore
git commit -m "refactor: add multi-stage Docker build to reduce image size"
```

---

## Task 3: Fix Dependency Leak di use_cases.py (#15)

### Task 3a: Tambah Protocol ke ports/agents.py

**Files:**
- Modify: `app/ports/agents.py`

- [ ] **Step 1: Tulis failing test untuk Protocol**

Buat `tests/domain/__init__.py` (kosong) dan `tests/domain/test_use_cases.py`:

```python
"""Unit tests HandleMessageUseCase — domain layer, zero adapter imports."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.domain.messaging import MessageContext
from app.domain.use_cases import HandleMessageUseCase
from app.intents.schemas import Intent


def _make_ctx(user_id: str = "u1", project_id: str = "p1") -> MessageContext:
    return MessageContext(
        user_id=user_id,
        conversation_id="chat-1",
        project_id=project_id,
        project_root=Path("/workspace"),
        project_name="test-project",
    )


def _make_intent(intent: str = "agent_code", confidence: float = 0.95) -> Intent:
    return Intent(intent=intent, confidence=confidence, reason="test")


def _make_use_case(**overrides: Any) -> HandleMessageUseCase:
    defaults: dict[str, Any] = dict(
        ai=MagicMock(),
        intent_parser=MagicMock(),
        plan_generator=MagicMock(),
        action_registry=MagicMock(),
        pending_plans=MagicMock(),
        history=MagicMock(),
    )
    defaults.update(overrides)
    return HandleMessageUseCase(**defaults)


def test_agent_delegation_yields_error_when_no_resolver() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    uc = _make_use_case(intent_parser=intent_parser, agent_resolver=None)
    events = list(uc.handle("refactor kode X", _make_ctx()))

    types = [e.type for e in events]
    assert "error" in types


def test_agent_delegation_yields_error_when_no_agent_configured() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    resolver = MagicMock()
    resolver.agent_for_role.return_value = None  # user belum config agent

    uc = _make_use_case(intent_parser=intent_parser, agent_resolver=resolver)
    events = list(uc.handle("refactor kode X", _make_ctx()))

    types = [e.type for e in events]
    assert "error" in types


def test_agent_delegation_yields_delegate_event() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_code")

    resolver = MagicMock()
    resolver.agent_for_role.return_value = "codex"

    uc = _make_use_case(intent_parser=intent_parser, agent_resolver=resolver)
    events = list(uc.handle("refactor kode X", _make_ctx()))

    types = [e.type for e in events]
    assert "delegate_to_agent" in types


def test_agent_delegation_uses_handoff_provider_when_present() -> None:
    intent_parser = MagicMock()
    intent_parser.parse.return_value = _make_intent("agent_review")

    resolver = MagicMock()
    resolver.agent_for_role.return_value = "claude"

    handoff = MagicMock()
    handoff.prepend_context.return_value = "[HANDOFF]\nreview kode X"

    uc = _make_use_case(
        intent_parser=intent_parser,
        agent_resolver=resolver,
        handoff_provider=handoff,
    )
    events = list(uc.handle("review kode X", _make_ctx()))

    handoff.prepend_context.assert_called_once()
    delegate_events = [e for e in events if e.type == "delegate_to_agent"]
    assert delegate_events
    assert "[HANDOFF]" in delegate_events[0].payload["prompt"]
```

- [ ] **Step 2: Jalankan test — harus FAIL karena Protocol belum ada**

```bash
cd /Users/anonymous/Documents/office/codinginid/ai-agent
pytest tests/domain/test_use_cases.py -v 2>&1 | head -30
```

Expected: error `TypeError` atau `unexpected keyword argument 'agent_resolver'`.

- [ ] **Step 3: Tambah Protocol ke ports/agents.py**

Ganti isi `app/ports/agents.py` dengan:

```python
from collections.abc import Sequence
from typing import Protocol

from app.domain.agents import AgentCapability


class AgentDiscoveryPort(Protocol):
    def discover(self) -> Sequence[AgentCapability]: ...


class AgentRoleResolver(Protocol):
    """Resolve (user_id, role) → agent CLI name dari persistent config."""

    def agent_for_role(self, user_id: str, role: str) -> str | None: ...


class HandoffContextProvider(Protocol):
    """Prepend konteks dari role sebelumnya ke prompt, kalau ada."""

    def prepend_context(self, project_id: str, role: str, prompt: str) -> str: ...
```

### Task 3b: Update HandleMessageUseCase

**Files:**
- Modify: `app/domain/use_cases.py`

- [ ] **Step 4: Tambah field Protocol ke dataclass dan update handle()**

Tambahkan dua field ke `HandleMessageUseCase` (setelah `execution_loop`):

```python
# Inject via composition.py — None = agent delegation disabled
agent_resolver: AgentRoleResolver | None = field(default=None)
handoff_provider: HandoffContextProvider | None = field(default=None)
```

Import Protocol di bagian import use_cases.py:

```python
from app.ports.agents import AgentRoleResolver, HandoffContextProvider
```

Ganti baris 169-188 di `handle()` (blok `if intent.is_agent()`) dengan:

```python
if intent.is_agent():
    role = _role_for_intent(intent.intent)
    if self.agent_resolver is None:
        yield ChatEvent.error(
            f"Agent resolver tidak tersedia untuk role '{role}'."
        )
        return
    agent_name = self.agent_resolver.agent_for_role(ctx.user_id, role)
    if agent_name is None:
        yield ChatEvent.error(
            f"Belum ada agent yang assigned untuk role '{role}'. "
            "Set via /agents di TUI atau Telegram."
        )
        return
    cleaned = _strip_command_prefix(text)
    if self.handoff_provider is not None:
        cleaned = self.handoff_provider.prepend_context(ctx.project_id, role, cleaned)
    yield ChatEvent.delegate_to_agent(
        agent=agent_name,
        prompt=cleaned,
        intent=intent.intent,
        role=role,
    )
    return
```

Hapus fungsi `_agent_for_intent` (lines 349-365) dan `_maybe_prepend_handoff` (lines 388-415) sepenuhnya dari `use_cases.py`.

- [ ] **Step 5: Jalankan test — harus PASS**

```bash
pytest tests/domain/test_use_cases.py -v
```

Expected: 4 test PASS.

### Task 3c: Buat adapter AgentRoleResolver

**Files:**
- Create: `app/adapters/agent_role_resolver.py`

- [ ] **Step 6: Buat adapter SqlAgentRoleResolver**

Buat file baru `app/adapters/agent_role_resolver.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.agent_configs import UserAgentConfigRepository


@dataclass
class SqlAgentRoleResolver:
    """AgentRoleResolver yang baca dari DB via UserAgentConfigRepository."""

    _factory: Any  # sessionmaker — type dari sqlalchemy, tidak diimport di sini

    def agent_for_role(self, user_id: str, role: str) -> str | None:
        return UserAgentConfigRepository(self._factory).agent_for_role(user_id, role)
```

### Task 3d: Buat adapter HandoffContextProvider

**Files:**
- Create: `app/adapters/handoff_context.py`

- [ ] **Step 7: Pindahkan logika _maybe_prepend_handoff ke adapter**

Buat file baru `app/adapters/handoff_context.py`:

```python
"""HandoffContextProvider — prepend output role sebelumnya ke prompt baru."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

# Role yang inherit context dari role sebelumnya.
_HANDOFF_FROM: dict[str, str] = {
    "reviewer":  "engineer",
    "architect": "engineer",
}


class RedisHandoffContextProvider:
    """Ambil last output role dari Redis dan prepend ke prompt."""

    def prepend_context(self, project_id: str, role: str, prompt: str) -> str:
        prev_role = _HANDOFF_FROM.get(role)
        if not prev_role:
            return prompt

        from app.adapters.agent_context import build_handoff_prefix, fetch_role

        def _run() -> dict[str, Any] | None:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(fetch_role(project_id, prev_role))
            finally:
                loop.close()

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                prev = pool.submit(_run).result(timeout=5)
        except Exception:
            return prompt

        if not prev:
            return prompt
        return build_handoff_prefix(prev, role) + prompt
```

### Task 3e: Wire ke composition.py

**Files:**
- Modify: `app/composition.py`

- [ ] **Step 8: Inject dua adapter baru ke build_use_case()**

Tambahkan import di atas `composition.py`:

```python
from app.adapters.agent_role_resolver import SqlAgentRoleResolver
from app.adapters.handoff_context import RedisHandoffContextProvider
```

Update fungsi `build_use_case()`:

```python
def build_use_case() -> HandleMessageUseCase:
    """Compose use case dengan semua dependensi konkret."""
    ollama = _ollama()
    return HandleMessageUseCase(
        ai=ollama,
        intent_parser=IntentParser(qwen_caller=ollama.chat),
        plan_generator=PlanGenerator(),
        action_registry=_build_action_registry(),
        pending_plans=_build_pending_plans(),
        history=SqlAlchemyChatHistory(_session_factory()),
        history_limit=settings.chat_history_limit,
        execution_loop=_execution_loop(),
        agent_resolver=SqlAgentRoleResolver(_session_factory()),
        handoff_provider=RedisHandoffContextProvider(),
    )
```

- [ ] **Step 9: Verifikasi tidak ada import adapter di domain layer**

```bash
grep -rn "from app.adapters\|from app.config" app/domain/
```

Expected: no output. Domain clean dari adapter imports.

- [ ] **Step 10: Jalankan full test suite**

```bash
cd /Users/anonymous/Documents/office/codinginid/ai-agent
make check
```

Expected: ruff ✓, mypy ✓, pytest ✓ (semua test hijau).

- [ ] **Step 11: Commit**

```bash
git add app/ports/agents.py app/domain/use_cases.py \
        app/adapters/agent_role_resolver.py app/adapters/handoff_context.py \
        app/composition.py \
        tests/domain/__init__.py tests/domain/test_use_cases.py
git commit -m "refactor(domain): fix dependency leak in use_cases.py via AgentRoleResolver port"
```

- [ ] **Step 12: Buat PR dan close issue**

```bash
git push origin refactor/multi-stage-docker  # atau branch yang sudah ada
gh issue close 15 --repo CodinginID/ai-agent \
  --comment "Fixed via PR — AgentRoleResolver + HandoffContextProvider Protocol di ports/agents.py. use_cases.py bebas dari adapter imports."
```

---

## Self-Review

**Spec coverage:**
- ✅ #18: close issue dengan comment
- ✅ #16: multi-stage Docker, `.dockerignore` update, before/after size
- ✅ #15: Protocol di ports/, adapter baru, injection di composition.py, domain clean test

**Placeholder scan:** tidak ada TBD atau TODO dalam kode di atas.

**Type consistency:**
- `AgentRoleResolver.agent_for_role(user_id, role)` → dipakai di use_cases step 4 dan adapter step 6 ✅
- `HandoffContextProvider.prepend_context(project_id, role, prompt)` → dipakai di use_cases step 4 dan adapter step 7 ✅
- Field `agent_resolver: AgentRoleResolver | None` dan `handoff_provider: HandoffContextProvider | None` → ditest di step 1 sebelum diimplementasi ✅
