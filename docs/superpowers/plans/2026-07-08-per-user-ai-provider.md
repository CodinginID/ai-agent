# Per-User AI Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membuat provider "otak" orchestrator (chat, summarize, planning, agentic loop, workflow roles) dapat dipilih **per-user** — Ollama/Qwen ATAU Claude ATAU provider lain — lewat `AgentConfig`/tabel preferensi, tanpa mengubah domain logic.

**Architecture:** Tambah port `AIProviderResolver` (`for_user(user_id) -> AIProvider`) dan sebuah **factory** `build_ai_provider(provider, model)` yang memetakan nama provider → adapter konkret dengan kredensial dari `config.py` (kredensial tetap server-side; user hanya memilih provider+model). Dua resolver: `StaticAIProviderResolver` (mempertahankan perilaku lama, dipakai test & mode single-provider) dan `DbAIProviderResolver` (baca preferensi per-user dari DB, cache instance per (provider, model)). `HandleMessageUseCase`, `ExecutionLoop`, dan `WorkflowOrchestrator` menerima resolver dan me-resolve provider di titik masuk memakai `ctx.user_id`. Semua tetap di balik port `AIProvider` (`chat`/`chat_stream`) yang sudah ada — hexagonal utuh.

**Tech Stack:** Python 3.13 · SQLAlchemy 2.x · Alembic · pytest/pytest-asyncio · `anthropic` SDK (adapter Claude) · `requests` (adapter Ollama, sudah ada).

## Global Constraints

- Domain (`app/domain/`, `app/ports/`) **zero import** dari adapter/framework eksternal — resolver & port hanya `Protocol`/dataclass murni.
- Type hint lengkap di semua signature (PEP 544 Protocol untuk port).
- Kredensial provider **tidak boleh** disimpan per-user di DB — hanya `provider` + `model`. API key/URL diambil dari `config.py` (env var) via `build_ai_provider`.
- Adapter baru wajib wrap error library eksternal → `AIProviderError` (`app/domain/exceptions.py`).
- Model Claude default: `claude-opus-4-8` (string ID persis, tanpa suffix tanggal).
- Adapter Claude memakai **official `anthropic` SDK**, bukan raw `requests`.
- Perubahan **backward-compatible**: tanpa preferensi user, resolver mengembalikan provider default (Ollama) — perilaku lama tak berubah.
- File < 500 baris. Test wajib untuk setiap unit baru; adapter ditest dengan mock (bukan hit jaringan nyata).
- Nama test: `test_<kondisi>_<expected_result>`.

---

### Task 1: Port `AIProviderResolver` + `StaticAIProviderResolver`

**Files:**
- Create: `app/ports/ai_provider_resolver.py`
- Create: `app/adapters/ai_provider_static.py`
- Test: `tests/adapters/test_ai_provider_static.py`

**Interfaces:**
- Consumes: `app.ports.ai_provider.AIProvider` (Protocol dengan `chat`/`chat_stream`).
- Produces: `AIProviderResolver` Protocol dengan `for_user(user_id: str) -> AIProvider`; `StaticAIProviderResolver(provider: AIProvider)` yang selalu mengembalikan `provider` yang sama.

- [ ] **Step 1: Write the failing test**

```python
# tests/adapters/test_ai_provider_static.py
from __future__ import annotations

from collections.abc import Iterator

from app.adapters.ai_provider_static import StaticAIProviderResolver


class _FakeProvider:
    def chat(self, prompt: str) -> str:
        return "ok"

    def chat_stream(self, prompt: str) -> Iterator[str]:
        yield "ok"


def test_for_user_returns_the_same_provider_for_any_user() -> None:
    provider = _FakeProvider()
    resolver = StaticAIProviderResolver(provider)
    assert resolver.for_user("user-1") is provider
    assert resolver.for_user("user-2") is provider
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/adapters/test_ai_provider_static.py -v`
Expected: FAIL — `ModuleNotFoundError: app.adapters.ai_provider_static`

- [ ] **Step 3: Write the port**

```python
# app/ports/ai_provider_resolver.py
"""Port untuk resolve AIProvider per-user.

Memungkinkan tiap user memilih provider (Ollama/Claude/dst) untuk otak
orchestrator. Domain hanya kenal abstraksi ini; resolusi konkret di adapter.
"""

from __future__ import annotations

from typing import Protocol

from app.ports.ai_provider import AIProvider


class AIProviderResolver(Protocol):
    def for_user(self, user_id: str) -> AIProvider: ...
```

- [ ] **Step 4: Write the static resolver**

```python
# app/adapters/ai_provider_static.py
"""Resolver yang selalu mengembalikan satu provider — mempertahankan perilaku
single-provider (dipakai test & saat DB preferensi tidak di-wire)."""

from __future__ import annotations

from dataclasses import dataclass

from app.ports.ai_provider import AIProvider


@dataclass(frozen=True)
class StaticAIProviderResolver:
    provider: AIProvider

    def for_user(self, user_id: str) -> AIProvider:
        return self.provider
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/adapters/test_ai_provider_static.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/ports/ai_provider_resolver.py app/adapters/ai_provider_static.py tests/adapters/test_ai_provider_static.py
git commit -m "feat(ports): AIProviderResolver + static resolver"
```

---

### Task 2: `AnthropicAdapter` (implement `AIProvider` via official SDK)

**Files:**
- Create: `app/adapters/anthropic.py`
- Test: `tests/adapters/test_anthropic_adapter.py`
- Modify: `requirements.txt` (tambah `anthropic`)

**Interfaces:**
- Produces: `AnthropicAdapter(api_key: str, model: str = "claude-opus-4-8", max_tokens: int = 16000)` implementing `AIProvider` — `chat(prompt) -> str`, `chat_stream(prompt) -> Iterator[str]`. Error `anthropic.APIError`/koneksi di-wrap jadi `AIProviderError`.

**Catatan API (dari skill claude-api):** default model `claude-opus-4-8`; `chat` pakai `client.messages.create(...)` lalu gabung text blocks (`b.text for b in resp.content if b.type == "text"`); `chat_stream` pakai `client.messages.stream(...).text_stream`; parameter `thinking` diomit (Opus 4.8 jalan tanpa thinking → paling cepat/murah, cocok untuk intent/chat/summarize). Jangan set `temperature`/`budget_tokens` (400 di Opus 4.8).

- [ ] **Step 1: Add dependency**

Edit `requirements.txt` — tambah baris (urut alfabet, setelah `anyio`):

```
anthropic>=0.92,<1.0
```

Lalu: `.venv/bin/pip install 'anthropic>=0.92,<1.0'`

- [ ] **Step 2: Write the failing test**

```python
# tests/adapters/test_anthropic_adapter.py
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.anthropic import AnthropicAdapter
from app.domain.exceptions import AIProviderError


class _FakeMessages:
    def __init__(self, blocks: list[Any] | Exception) -> None:
        self._blocks = blocks

    def create(self, **kwargs: Any) -> Any:
        if isinstance(self._blocks, Exception):
            raise self._blocks
        return SimpleNamespace(content=self._blocks)


def _text_block(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)


def test_chat_joins_text_blocks() -> None:
    adapter = AnthropicAdapter(api_key="k", model="claude-opus-4-8")
    adapter._client = SimpleNamespace(  # type: ignore[attr-defined]
        messages=_FakeMessages([_text_block("hello "), _text_block("world")])
    )
    assert adapter.chat("hi") == "hello world"


def test_chat_wraps_sdk_error_as_domain_error() -> None:
    adapter = AnthropicAdapter(api_key="k")
    adapter._client = SimpleNamespace(  # type: ignore[attr-defined]
        messages=_FakeMessages(RuntimeError("boom"))
    )
    with pytest.raises(AIProviderError):
        adapter.chat("hi")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/adapters/test_anthropic_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: app.adapters.anthropic`

- [ ] **Step 4: Write the adapter**

```python
# app/adapters/anthropic.py
"""Anthropic (Claude) adapter — implement ``AIProvider`` port via SDK resmi.

``chat`` blocking (gabung text blocks); ``chat_stream`` streaming token.
Parameter thinking sengaja diomit — Opus 4.8 jalan tanpa thinking, paling
cepat/murah untuk intent classify, chat, dan summarize.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import anthropic

from app.domain.exceptions import AIProviderError

_DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class AnthropicAdapter:
    api_key: str
    model: str = _DEFAULT_MODEL
    max_tokens: int = 16000
    _client: anthropic.Anthropic = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=self.api_key)

    def chat(self, prompt: str) -> str:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # SDK exceptions + koneksi
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc
        return "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()

    def chat_stream(self, prompt: str) -> Iterator[str]:
        try:
            with self._client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                yield from stream.text_stream
        except Exception as exc:
            raise AIProviderError(f"Anthropic stream failed: {exc}") from exc
```

> Catatan gaya: CLAUDE.md melarang `except Exception` generik. Di sini di-terima sebagai *boundary adapter* (mem-wrap seluruh kegagalan library eksternal → domain error) — pola yang sama sudah dipakai `PMAgent`. Jika reviewer menolak, persempit ke `(anthropic.APIError, anthropic.APIConnectionError)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/adapters/test_anthropic_adapter.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/adapters/anthropic.py tests/adapters/test_anthropic_adapter.py requirements.txt
git commit -m "feat(adapters): AnthropicAdapter implementing AIProvider"
```

---

### Task 3: Provider factory + config

**Files:**
- Create: `app/adapters/ai_provider_factory.py`
- Modify: `app/config.py` (tambah field `ai_provider_default`, `anthropic_api_key`, `anthropic_model`, `anthropic_max_tokens`)
- Modify: `.env.example`
- Test: `tests/adapters/test_ai_provider_factory.py`

**Interfaces:**
- Consumes: `OllamaAdapter`, `AnthropicAdapter`, `app.config.Settings`.
- Produces: `build_ai_provider(provider: str, model: str | None, settings: Settings) -> AIProvider`. `provider` ∈ `{"ollama", "anthropic"}` (alias `"claude"` → `"anthropic"`). `model=None` → default per provider. Provider tak dikenal → `ValueError`.

- [ ] **Step 1: Add config fields**

Edit `app/config.py` — tambah di dalam `class Settings` (setelah blok RAG, sebelum penutup dataclass):

```python
    # ── AI provider selection ─────────────────────────────────────────────────
    ai_provider_default: str    # "ollama" | "anthropic"
    anthropic_api_key: str
    anthropic_model: str
    anthropic_max_tokens: int
```

Dan di `load_settings()` (dekat blok RAG, sebelum `return`):

```python
        ai_provider_default=os.getenv("AI_PROVIDER_DEFAULT", "ollama").strip().lower(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8").strip(),
        anthropic_max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "16000")),
```

- [ ] **Step 2: Update `.env.example`** — tambah blok:

```
# ── AI provider (otak orchestrator) ──────────────────────────────────────────
# Provider default kalau user belum memilih: ollama | anthropic
AI_PROVIDER_DEFAULT=ollama
# Kredensial Claude (server-side; user hanya memilih provider+model)
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-opus-4-8
ANTHROPIC_MAX_TOKENS=16000
```

- [ ] **Step 3: Write the failing test**

```python
# tests/adapters/test_ai_provider_factory.py
from __future__ import annotations

import pytest

from app.adapters.ai_provider_factory import build_ai_provider
from app.adapters.anthropic import AnthropicAdapter
from app.adapters.ollama import OllamaAdapter
from app.config import load_settings


def _settings():
    return load_settings()


def test_ollama_provider_returns_ollama_adapter() -> None:
    provider = build_ai_provider("ollama", None, _settings())
    assert isinstance(provider, OllamaAdapter)


def test_claude_alias_maps_to_anthropic_adapter() -> None:
    s = _settings()
    provider = build_ai_provider("claude", "claude-opus-4-8", s)
    assert isinstance(provider, AnthropicAdapter)
    assert provider.model == "claude-opus-4-8"


def test_model_none_uses_provider_default() -> None:
    provider = build_ai_provider("anthropic", None, _settings())
    assert isinstance(provider, AnthropicAdapter)
    assert provider.model == "claude-opus-4-8"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        build_ai_provider("gpt", None, _settings())
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/adapters/test_ai_provider_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: app.adapters.ai_provider_factory`

- [ ] **Step 5: Write the factory**

```python
# app/adapters/ai_provider_factory.py
"""Factory: (provider, model) → AIProvider konkret dengan kredensial server-side.

Kredensial (API key/URL) diambil dari Settings — TIDAK pernah dari DB per-user.
User hanya memilih nama provider + model.
"""

from __future__ import annotations

from app.adapters.anthropic import AnthropicAdapter
from app.adapters.ollama import OllamaAdapter
from app.config import Settings
from app.ports.ai_provider import AIProvider

_ALIASES = {"claude": "anthropic"}


def build_ai_provider(
    provider: str, model: str | None, settings: Settings
) -> AIProvider:
    name = _ALIASES.get(provider.strip().lower(), provider.strip().lower())
    if name == "ollama":
        return OllamaAdapter(
            url=settings.qwen_url,
            model=model or settings.qwen_model,
            timeout=settings.command_timeout * 3,
        )
    if name == "anthropic":
        return AnthropicAdapter(
            api_key=settings.anthropic_api_key,
            model=model or settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )
    raise ValueError(f"Unknown AI provider: {provider!r}")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/adapters/test_ai_provider_factory.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/adapters/ai_provider_factory.py app/config.py .env.example tests/adapters/test_ai_provider_factory.py
git commit -m "feat(config): AI provider factory + provider/model settings"
```

---

### Task 4: Per-user provider preference (table + repository + migration)

**Files:**
- Modify: `app/adapters/database/models.py` (tambah `UserProviderConfigModel`)
- Create: `app/adapters/user_provider_config.py`
- Create: `alembic/versions/20260708_0009_user_provider_config.py`
- Test: `tests/adapters/test_user_provider_config.py`

**Interfaces:**
- Produces: `UserProviderConfigRepository(factory)` — `get(user_id) -> tuple[str, str | None] | None` (provider, model) dan `set(user_id, provider, model=None) -> None` (upsert). Satu baris per user (unique `user_id`).

- [ ] **Step 1: Add the model**

Edit `app/adapters/database/models.py` — tambah class (ikuti pola `UserAgentConfigModel`):

```python
class UserProviderConfigModel(Base):
    """Pilihan provider "otak" orchestrator per-user (satu baris per user).

    Hanya menyimpan nama provider + model — kredensial tetap di config server.
    """

    __tablename__ = "user_provider_configs"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(40))  # ollama, anthropic
    model: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
```

- [ ] **Step 2: Write the failing test**

```python
# tests/adapters/test_user_provider_config.py
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.database.models import Base, UserModel
from app.adapters.user_provider_config import UserProviderConfigRepository


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as s:
        s.add(UserModel(id="u1", email="a@b.c"))
        s.commit()
    return factory


def test_get_returns_none_when_unset(factory) -> None:
    assert UserProviderConfigRepository(factory).get("u1") is None


def test_set_then_get_roundtrip(factory) -> None:
    repo = UserProviderConfigRepository(factory)
    repo.set("u1", "anthropic", "claude-opus-4-8")
    assert repo.get("u1") == ("anthropic", "claude-opus-4-8")


def test_set_is_upsert(factory) -> None:
    repo = UserProviderConfigRepository(factory)
    repo.set("u1", "anthropic", "claude-opus-4-8")
    repo.set("u1", "ollama", None)
    assert repo.get("u1") == ("ollama", None)
```

> Cek `UserModel` punya kolom `id` + `email` — sesuaikan konstruksi seed kalau signature-nya beda (lihat `app/adapters/database/models.py`).

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/adapters/test_user_provider_config.py -v`
Expected: FAIL — `ModuleNotFoundError: app.adapters.user_provider_config`

- [ ] **Step 4: Write the repository**

```python
# app/adapters/user_provider_config.py
"""Repository preferensi provider per-user."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.adapters.database.models import UserProviderConfigModel

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


class UserProviderConfigRepository:
    def __init__(self, factory: sessionmaker[Any]) -> None:
        self._factory = factory

    def get(self, user_id: str) -> tuple[str, str | None] | None:
        with self._factory() as session:
            row = session.get(UserProviderConfigModel, user_id)
            return (row.provider, row.model) if row else None

    def set(self, user_id: str, provider: str, model: str | None = None) -> None:
        with self._factory() as session:
            row = session.get(UserProviderConfigModel, user_id)
            if row is None:
                session.add(
                    UserProviderConfigModel(
                        user_id=user_id, provider=provider, model=model
                    )
                )
            else:
                row.provider = provider
                row.model = model
            session.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/adapters/test_user_provider_config.py -v`
Expected: PASS

- [ ] **Step 6: Write the Alembic migration**

Lihat header revisi terbaru (`alembic/versions/20260518_0008_skills_table.py`) untuk `down_revision`, lalu:

```python
# alembic/versions/20260708_0009_user_provider_config.py
"""user provider config

Revision ID: 0009_user_provider_config
Revises: 0008_skills_table
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_user_provider_config"
down_revision = "0008_skills_table"  # SESUAIKAN dengan revision id di file 0008
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_provider_configs",
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_provider_configs")
```

> Verifikasi `revision`/`down_revision` string persis dari file 0008 (buka file itu — id-nya bisa beda dari nama file).

- [ ] **Step 7: Commit**

```bash
git add app/adapters/database/models.py app/adapters/user_provider_config.py alembic/versions/20260708_0009_user_provider_config.py tests/adapters/test_user_provider_config.py
git commit -m "feat(db): per-user provider config table + repository"
```

---

### Task 5: `DbAIProviderResolver`

**Files:**
- Create: `app/adapters/ai_provider_db.py`
- Test: `tests/adapters/test_ai_provider_db.py`

**Interfaces:**
- Consumes: `UserProviderConfigRepository`, `build_ai_provider`, `Settings`.
- Produces: `DbAIProviderResolver(repo, settings)` implementing `AIProviderResolver`. `for_user(user_id)`: baca preferensi user → kalau ada, `build_ai_provider(provider, model, settings)`; kalau tidak, pakai `settings.ai_provider_default`. Cache instance per `(provider, model)` supaya tidak rebuild tiap request.

- [ ] **Step 1: Write the failing test**

```python
# tests/adapters/test_ai_provider_db.py
from __future__ import annotations

from app.adapters.ai_provider_db import DbAIProviderResolver
from app.adapters.anthropic import AnthropicAdapter
from app.adapters.ollama import OllamaAdapter
from app.config import load_settings


class _FakeRepo:
    def __init__(self, mapping: dict[str, tuple[str, str | None]]) -> None:
        self._m = mapping

    def get(self, user_id: str) -> tuple[str, str | None] | None:
        return self._m.get(user_id)


def test_user_with_preference_gets_chosen_provider() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), load_settings()
    )
    assert isinstance(resolver.for_user("u1"), AnthropicAdapter)


def test_user_without_preference_gets_default() -> None:
    resolver = DbAIProviderResolver(_FakeRepo({}), load_settings())
    assert isinstance(resolver.for_user("u1"), OllamaAdapter)  # AI_PROVIDER_DEFAULT=ollama


def test_same_provider_model_is_cached() -> None:
    resolver = DbAIProviderResolver(
        _FakeRepo({"u1": ("anthropic", "claude-opus-4-8")}), load_settings()
    )
    assert resolver.for_user("u1") is resolver.for_user("u1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/adapters/test_ai_provider_db.py -v`
Expected: FAIL — `ModuleNotFoundError: app.adapters.ai_provider_db`

- [ ] **Step 3: Write the resolver**

```python
# app/adapters/ai_provider_db.py
"""Resolver per-user berbasis DB — baca preferensi, bangun provider, cache."""

from __future__ import annotations

from typing import Protocol

from app.adapters.ai_provider_factory import build_ai_provider
from app.config import Settings
from app.ports.ai_provider import AIProvider


class _PrefReader(Protocol):
    def get(self, user_id: str) -> tuple[str, str | None] | None: ...


class DbAIProviderResolver:
    def __init__(self, repo: _PrefReader, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings
        self._cache: dict[tuple[str, str | None], AIProvider] = {}

    def for_user(self, user_id: str) -> AIProvider:
        pref = self._repo.get(user_id)
        provider, model = pref if pref else (self._settings.ai_provider_default, None)
        key = (provider, model)
        cached = self._cache.get(key)
        if cached is None:
            cached = build_ai_provider(provider, model, self._settings)
            self._cache[key] = cached
        return cached
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/adapters/test_ai_provider_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/adapters/ai_provider_db.py tests/adapters/test_ai_provider_db.py
git commit -m "feat(adapters): DbAIProviderResolver with per-provider caching"
```

---

### Task 6: `HandleMessageUseCase` — resolve provider per-user (chat + summarize)

**Files:**
- Modify: `app/domain/use_cases.py`
- Test: `tests/domain/test_use_cases.py`

**Interfaces:**
- Consumes: `AIProviderResolver` (Task 1). `HandleMessageUseCase.ai` tetap ada sebagai default/fallback.
- Produces: field baru `provider_resolver: AIProviderResolver | None = None`. Helper `_resolve_ai(user_id) -> AIProvider` = `provider_resolver.for_user(user_id)` kalau ada, else `self.ai`. `_handle_chat`/`_handle_action` menerima parameter `ai: AIProvider`.

**Scope increment ini:** chat + summarize memakai provider per-user. Intent classification (`IntentParser`) dan `ExecutionLoop` di Task berikutnya (7). Ini bukan silent cap — didokumentasikan di sini.

- [ ] **Step 1: Write the failing test**

```python
# tambahkan ke tests/domain/test_use_cases.py
from collections.abc import Iterator


class _ResolverProvider:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.seen: list[str] = []

    def chat(self, prompt: str) -> str:
        return f"{self.tag}:summary"

    def chat_stream(self, prompt: str) -> Iterator[str]:
        self.seen.append(prompt)
        yield f"{self.tag}:reply"


class _Resolver:
    def __init__(self, provider: _ResolverProvider) -> None:
        self._p = provider

    def for_user(self, user_id: str) -> _ResolverProvider:
        return self._p


def test_chat_uses_resolved_per_user_provider() -> None:
    # Rakit HandleMessageUseCase memakai fake yang sudah ada di file ini
    # (intent_parser mengembalikan intent chat), lalu:
    per_user = _ResolverProvider("claude")
    use_case = _build_chat_use_case(provider_resolver=_Resolver(per_user))  # helper test setempat
    events = list(use_case.handle("halo", _ctx(user_id="u1")))
    assert any(e.type == ChatEventType.TEXT_CHUNK and "claude:reply" in e.payload.get("text", "")
               for e in events)
    assert per_user.seen, "provider per-user harus dipakai untuk chat_stream"
```

> Ikuti pola fake/`_ctx` yang sudah ada di `tests/domain/test_use_cases.py`. Kalau belum ada helper perakitan, tulis satu yang meng-inject `ai=<default fake>`, `provider_resolver=<resolver>`, dan `intent_parser` yang mengembalikan intent non-action non-agent (→ jalur chat).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/domain/test_use_cases.py -k per_user -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'provider_resolver'`

- [ ] **Step 3: Add the field + resolve helper**

Edit `app/domain/use_cases.py`:

Tambah import di blok ports:
```python
from app.ports.ai_provider_resolver import AIProviderResolver
```

Tambah field (setelah `context_provider`):
```python
    # Optional — resolve provider per-user untuk chat/summarize. None → pakai self.ai.
    provider_resolver: AIProviderResolver | None = field(default=None)
```

Tambah helper (di bagian private, dekat `_audit`):
```python
    def _resolve_ai(self, user_id: str) -> AIProvider:
        if self.provider_resolver is not None:
            return self.provider_resolver.for_user(user_id)
        return self.ai
```

- [ ] **Step 4: Thread `ai` ke jalur chat & action**

Di `_handle_inner`, ganti dua pemanggilan:
```python
        # ── 3. Chat path ──────────────────────────────────────────────────────
        if not intent.is_action():
            yield from self._handle_chat(self._resolve_ai(ctx.user_id), text, ctx)
            return
```
```python
        # ── 5. Simple action path ─────────────────────────────────────────────
        yield from self._handle_action(self._resolve_ai(ctx.user_id), text, intent, ctx)
```

Ubah signature + body `_handle_chat` untuk menerima `ai`:
```python
    def _handle_chat(self, ai: AIProvider, text: str, ctx: MessageContext) -> Iterator[ChatEvent]:
        ...
            for chunk in ai.chat_stream(prompt):   # ganti self.ai → ai
```

Ubah signature + body `_handle_action` untuk menerima `ai` dan pakai di summarize:
```python
    def _handle_action(
        self, ai: AIProvider, text: str, intent: Intent, ctx: MessageContext
    ) -> Iterator[ChatEvent]:
        ...
            summary = ai.chat(_SUMMARIZE_PROMPT.format(output=result))  # ganti self.ai → ai
```

- [ ] **Step 5: Run test + full suite**

Run: `.venv/bin/python -m pytest tests/domain/test_use_cases.py -v && .venv/bin/python -m pytest tests/ -q`
Expected: PASS (semua hijau — `self.ai` fallback menjaga test lama)

- [ ] **Step 6: Commit**

```bash
git add app/domain/use_cases.py tests/domain/test_use_cases.py
git commit -m "feat(domain): resolve AI provider per-user for chat and summarize"
```

---

### Task 7: `ExecutionLoop` provider per-user

**Files:**
- Modify: `app/ports/execution_loop.py`
- Modify: `app/executor/loop.py`
- Modify: `app/domain/use_cases.py` (`_handle_loop` teruskan provider)
- Test: `tests/executor/test_loop.py`

**Interfaces:**
- `ExecutionLoopPort.run(prompt, history="", *, ai: AIProvider | None = None)` — `ai` override opsional; default `None` → pakai `self.ai` (backward-compatible).
- `HandleMessageUseCase._handle_loop` memanggil `self.execution_loop.run(text, history=history_text, ai=self._resolve_ai(ctx.user_id))`.

- [ ] **Step 1: Write the failing test** — di `tests/executor/test_loop.py`, verifikasi bila `run(..., ai=fake)` diberikan, `fake.chat` dipakai untuk langkah THINK (bukan `self.ai`). Ikuti fixture loop yang sudah ada; assert prompt diterima oleh fake override.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/executor/test_loop.py -k override -v`
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'ai'`

- [ ] **Step 3: Update port**

```python
# app/ports/execution_loop.py
from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.ports.ai_provider import AIProvider


class ExecutionLoopPort(Protocol):
    def run(
        self, prompt: str, history: str = "", *, ai: "AIProvider | None" = None
    ) -> Iterator[Any]: ...
```

- [ ] **Step 4: Update loop** — di `app/executor/loop.py`:

```python
    def run(
        self,
        prompt: str,
        history: str = "",
        *,
        ai: AIProvider | None = None,
    ) -> Iterator[LoopEvent]:
        active_ai = ai or self.ai
        ...
        # ganti setiap self.ai.chat(...) → active_ai.chat(...) di dalam run()
```

- [ ] **Step 5: Update `_handle_loop`** — di `app/domain/use_cases.py`:

```python
            for loop_ev in self.execution_loop.run(
                text, history=history_text, ai=self._resolve_ai(ctx.user_id)
            ):
```

- [ ] **Step 6: Run tests**

Run: `.venv/bin/python -m pytest tests/executor/test_loop.py tests/domain/test_use_cases.py -v && .venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/ports/execution_loop.py app/executor/loop.py app/domain/use_cases.py tests/executor/test_loop.py
git commit -m "feat(executor): per-user AI provider override in ExecutionLoop"
```

---

### Task 8: Wiring composition + `IntentParser` provider-aware

**Files:**
- Modify: `app/composition.py`
- Modify: `app/domain/use_cases.py` + `app/intents/parser.py` (intent classify pakai provider per-user)
- Test: `tests/test_composition_rag.py` atau test komposisi baru (smoke: `build_use_case()` tetap membangun objek valid)

**Interfaces:**
- `IntentParser` sudah menerima `qwen_caller: Callable[[str], str]`. Agar per-user, use case memanggil parser dengan caller dari provider ter-resolve. Pendekatan minim-invasif: `HandleMessageUseCase` menyimpan `intent_parser` default (untuk fallback) DAN, saat `provider_resolver` ada, bangun caller `self._resolve_ai(ctx.user_id).chat` lalu panggil `self.intent_parser.parse_with(caller, text, project_id)`.

- [ ] **Step 1:** Tambah method `IntentParser.parse_with(self, caller: Callable[[str], str], text: str, project_id: str) -> Intent` yang identik dengan `parse` tapi memakai `caller` alih-alih `self._qwen_caller`. `parse` menjadi `return self.parse_with(self._qwen_caller, text, project_id)`. Tulis test unit di `tests/intents/test_parser.py` (caller di-inject dipakai).

- [ ] **Step 2:** Di `_handle_inner`, ganti:
```python
            intent = self.intent_parser.parse_with(
                self._resolve_ai(ctx.user_id).chat, text, ctx.project_id
            )
```

- [ ] **Step 3: Wire resolver di `app/composition.py`.** Tambah factory + inject:

```python
@lru_cache(maxsize=1)
def _ai_provider_resolver() -> "AIProviderResolver":
    from app.adapters.ai_provider_db import DbAIProviderResolver
    from app.adapters.user_provider_config import UserProviderConfigRepository
    return DbAIProviderResolver(
        UserProviderConfigRepository(_session_factory()), settings
    )
```

Di `build_use_case()` tambah argumen:
```python
        provider_resolver=_ai_provider_resolver(),
```

`_ollama()` tetap dipakai sebagai `ai=` default/fallback (aman bila resolver mengembalikan Ollama juga). `_execution_loop()` dan `_workflow_orchestrator()` tetap dibangun dengan Ollama default; override per-user datang lewat argumen `ai=` di runtime (Task 7 & 8-workflow).

- [ ] **Step 4:** Jalankan seluruh suite: `.venv/bin/python -m pytest tests/ -q` → semua hijau.

- [ ] **Step 5: Commit**

```bash
git add app/composition.py app/domain/use_cases.py app/intents/parser.py tests/
git commit -m "feat(composition): wire per-user provider resolver into use case + intent"
```

---

### Task 9: `WorkflowOrchestrator` roles provider per-user (opsional, untuk "semua")

**Files:**
- Modify: `app/adapters/workflow_fallback.py` (Prompt{Architect,Engineer,Reviewer} terima provider per panggilan) atau bangun orchestrator per-user di interface `/workflow`.
- Modify: `app/interfaces/workflow.py` (resolve provider dari user_id sebelum `plan`/`implement`)
- Test: `tests/orchestrator/test_workflow.py`, `tests/interfaces/test_workflow_endpoints.py`

**Pendekatan:** Karena `/workflow` endpoint sudah punya `_resolve_user_id`, bangun `WorkflowOrchestrator` per-request dengan `PromptArchitect/Engineer/Reviewer(ai=resolver.for_user(uid), model=<label>)`. Karena aturan `require_distinct_models` **sudah dihapus**, ketiga role boleh memakai provider+model yang sama (satu Claude untuk semua) tanpa error.

- [ ] **Step 1:** Tambah factory `build_workflow_orchestrator_for_user(user_id)` di `app/composition.py` yang me-resolve provider lalu merakit role adapters + `FileArtifactStore`/`RepoFileChecker`/audit (reuse yang sudah ada).
- [ ] **Step 2:** Di `app/interfaces/workflow.py`, ganti `_orchestrator()` → `_orchestrator_for(uid)` memakai factory itu.
- [ ] **Step 3:** Test: endpoint plan/implement tetap 200; unit orchestrator dengan engineer==reviewer model **tidak** error (regresi guard, sejalan penghapusan `require_distinct_models`).
- [ ] **Step 4: Commit**

```bash
git add app/composition.py app/interfaces/workflow.py app/adapters/workflow_fallback.py tests/
git commit -m "feat(workflow): per-user provider for architect/engineer/reviewer roles"
```

---

### Task 10: Perintah pemilih provider (`/provider`) di TUI & Telegram

**Files:**
- Modify: `app/handlers/commands.py` (Telegram) + `app/tui/_commands.py` (TUI)
- Modify: handler registry terkait
- Test: test handler command terkait

**Interfaces:** `/provider` tanpa argumen → tampilkan provider aktif + daftar pilihan (`ollama`, `anthropic`). `/provider <name> [model]` → `UserProviderConfigRepository.set(user_id, name, model)` + konfirmasi. Validasi `name` lewat `build_ai_provider` (tangkap `ValueError` → pesan ramah). Cerminan pola `/agents`.

- [ ] **Step 1–5:** TDD per handler (tampilkan, set valid, set invalid → error ramah, persist), lalu commit:

```bash
git commit -m "feat(cli): /provider command to pick per-user AI provider"
```

---

## Self-Review

**Spec coverage:**
- "Provider bisa dipilih per-user (Ollama/Claude/lain)" → Task 1–5 (resolver, factory, adapter, tabel, DB resolver), Task 10 (UI pilih).
- "Untuk semua termasuk orchestrator" → chat/summarize (Task 6), agentic loop (Task 7), intent classify (Task 8), workflow roles (Task 9).
- "require_distinct_models salah" → sudah dihapus sebelum plan ini (commit terpisah); Task 9 mengandalkan itu (engineer==reviewer boleh sama).
- "Menentukan spek device user" → Arah C fleksibel: kredensial server-side (factory), device tetap ringan; didokumentasikan di Global Constraints.

**Placeholder scan:** Tidak ada TODO/TBD. Kode lengkap untuk unit baru (Task 1–5); Task 6–7 diff presisi dengan kode; Task 8–10 langkah konkret dengan signature eksplisit (`parse_with`, `run(..., ai=)`, factory names).

**Type consistency:** `AIProviderResolver.for_user(user_id: str) -> AIProvider` konsisten dipakai di Task 1/5/6/7/8. `build_ai_provider(provider, model, settings)` signature sama di Task 3/5. `UserProviderConfigRepository.get -> tuple[str, str|None] | None` dipakai konsisten di Task 4/5. `ExecutionLoopPort.run(..., *, ai=None)` selaras di Task 7.

**Catatan urutan:** Task 6 bisa merah bila resolver belum di-wire — aman karena `provider_resolver` default `None` (fallback `self.ai`); wiring nyata di Task 8. ExecutionLoop (7) & workflow (9) mandiri per-Task.
