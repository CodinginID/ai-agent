"""Unit tests for agent_context scratchpad — Redis mocked dengan fake in-memory store."""

from __future__ import annotations

from typing import Any

import pytest

from app.adapters.agent_context import (
    MAX_OUTPUT_BYTES,
    build_handoff_prefix,
    clear,
    fetch_role,
    purge_legacy_keys,
    store_result,
)


class FakeAsyncRedis:
    """In-memory fake yang implement subset method redis-async yang dipakai
    oleh agent_context: hset/hgetall/expire/delete/scan.

    Cukup faithful untuk verifikasi isolasi antar key dan behaviour purge.
    """

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._expirations: dict[str, int] = {}

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        bucket = self._hashes.setdefault(key, {})
        new_fields = sum(1 for f in mapping if f not in bucket)
        for f, v in mapping.items():
            bucket[f] = str(v)
        return new_fields

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def expire(self, key: str, ttl: int) -> int:
        if key not in self._hashes:
            return 0
        self._expirations[key] = ttl
        return 1

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self._hashes:
                del self._hashes[k]
                self._expirations.pop(k, None)
                n += 1
        return n

    async def scan(
        self, cursor: int = 0, match: str | None = None, count: int = 10
    ) -> tuple[int, list[str]]:
        # Implementasi sederhana: 1 batch saja, lalu cursor=0 menandakan selesai.
        prefix = ""
        if match and match.endswith("*"):
            prefix = match[:-1]
        keys = [k for k in self._hashes if not prefix or k.startswith(prefix)]
        return 0, keys


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeAsyncRedis:
    fake = FakeAsyncRedis()
    monkeypatch.setattr("app.adapters.agent_context.get_client", lambda: fake)
    return fake


# ── store_result + fetch_role ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_then_fetch_round_trip(fake_redis: FakeAsyncRedis) -> None:
    await store_result(
        "proj-1", "engineer",
        agent="codex", prompt="refactor X", output="done.", summary="OK",
    )
    got = await fetch_role("proj-1", "engineer")
    assert got is not None
    assert got["agent"] == "codex"
    assert got["prompt"] == "refactor X"
    assert got["output"] == "done."
    assert got["summary"] == "OK"
    assert got["truncated"] == "false"
    assert "finished_at" in got


@pytest.mark.asyncio
async def test_two_projects_do_not_overwrite_each_other(fake_redis: FakeAsyncRedis) -> None:
    """Acceptance criteria utama: 2 project paralel tidak saling overwrite."""
    await store_result(
        "proj-A", "engineer",
        agent="codex", prompt="A prompt", output="A output", summary="",
    )
    await store_result(
        "proj-B", "engineer",
        agent="claude", prompt="B prompt", output="B output", summary="",
    )

    a = await fetch_role("proj-A", "engineer")
    b = await fetch_role("proj-B", "engineer")

    assert a is not None and b is not None
    assert a["output"] == "A output"
    assert a["agent"] == "codex"
    assert b["output"] == "B output"
    assert b["agent"] == "claude"


@pytest.mark.asyncio
async def test_fetch_missing_returns_none(fake_redis: FakeAsyncRedis) -> None:
    assert await fetch_role("proj-empty", "engineer") is None


@pytest.mark.asyncio
async def test_output_truncated_when_exceeds_max_bytes(fake_redis: FakeAsyncRedis) -> None:
    huge = "x" * (MAX_OUTPUT_BYTES + 100)
    await store_result(
        "proj-1", "engineer",
        agent="codex", prompt="p", output=huge,
    )
    got = await fetch_role("proj-1", "engineer")
    assert got is not None
    assert len(got["output"]) == MAX_OUTPUT_BYTES
    assert got["truncated"] == "true"


# ── clear ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_specific_role_only(fake_redis: FakeAsyncRedis) -> None:
    await store_result("proj-1", "engineer", agent="codex", prompt="p", output="o")
    await store_result("proj-1", "reviewer", agent="claude", prompt="p", output="o")

    n = await clear("proj-1", "engineer")
    assert n == 1
    assert await fetch_role("proj-1", "engineer") is None
    assert await fetch_role("proj-1", "reviewer") is not None


@pytest.mark.asyncio
async def test_clear_all_deletes_every_known_role(fake_redis: FakeAsyncRedis) -> None:
    for role in ("engineer", "reviewer", "architect"):
        await store_result("proj-1", role, agent="x", prompt="p", output="o")

    n = await clear("proj-1", role=None)
    assert n == 3
    for role in ("engineer", "reviewer", "architect"):
        assert await fetch_role("proj-1", role) is None


@pytest.mark.asyncio
async def test_clear_project_does_not_touch_other_project(fake_redis: FakeAsyncRedis) -> None:
    await store_result("proj-A", "engineer", agent="x", prompt="p", output="o")
    await store_result("proj-B", "engineer", agent="x", prompt="p", output="o")

    await clear("proj-A", role=None)
    assert await fetch_role("proj-A", "engineer") is None
    assert await fetch_role("proj-B", "engineer") is not None


# ── build_handoff_prefix ────────────────────────────────────────────────────


def test_build_handoff_prefix_includes_prev_output_and_role() -> None:
    prev = {
        "agent": "codex",
        "prompt": "do X",
        "output": "<patch>",
        "truncated": "false",
    }
    prefix = build_handoff_prefix(prev, "reviewer")
    assert "codex" in prefix
    assert "do X" in prefix
    assert "<patch>" in prefix
    assert "Sebagai reviewer" in prefix
    assert "(truncated)" not in prefix


def test_build_handoff_prefix_marks_truncated() -> None:
    prev = {"agent": "codex", "prompt": "p", "output": "o", "truncated": "true"}
    assert "(truncated)" in build_handoff_prefix(prev, "reviewer")


# ── purge_legacy_keys ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_purge_legacy_keys_deletes_only_pre_project_format(
    fake_redis: FakeAsyncRedis,
) -> None:
    # Seed campuran: 2 legacy keys + 1 key baru (project-scoped).
    fake_redis._hashes["agent:ctx:user-123:engineer"] = {"agent": "codex"}
    fake_redis._hashes["agent:ctx:user-456:reviewer"] = {"agent": "claude"}
    fake_redis._hashes["agent:ctx:proj:proj-A:engineer"] = {"agent": "codex"}

    deleted = await purge_legacy_keys()

    assert deleted == 2
    assert "agent:ctx:user-123:engineer" not in fake_redis._hashes
    assert "agent:ctx:user-456:reviewer" not in fake_redis._hashes
    assert "agent:ctx:proj:proj-A:engineer" in fake_redis._hashes


@pytest.mark.asyncio
async def test_purge_legacy_keys_idempotent(fake_redis: FakeAsyncRedis) -> None:
    fake_redis._hashes["agent:ctx:proj:proj-A:engineer"] = {"agent": "codex"}
    first = await purge_legacy_keys()
    second = await purge_legacy_keys()
    assert first == 0
    assert second == 0
    assert "agent:ctx:proj:proj-A:engineer" in fake_redis._hashes


@pytest.mark.asyncio
async def test_purge_with_empty_redis_returns_zero(fake_redis: FakeAsyncRedis) -> None:
    assert await purge_legacy_keys() == 0


# ── failure surface (Redis exception) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_store_swallows_redis_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis down jangan crash flow utama — adapter cuma log."""

    class Broken:
        async def hset(self, *a: Any, **kw: Any) -> int:
            raise ConnectionError("redis down")

    monkeypatch.setattr("app.adapters.agent_context.get_client", lambda: Broken())
    # tidak boleh raise
    await store_result("proj-1", "engineer", agent="x", prompt="p", output="o")


@pytest.mark.asyncio
async def test_fetch_returns_none_on_redis_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        async def hgetall(self, *a: Any, **kw: Any) -> dict[str, str]:
            raise ConnectionError("redis down")

    monkeypatch.setattr("app.adapters.agent_context.get_client", lambda: Broken())
    assert await fetch_role("proj-1", "engineer") is None


# ── redis_client key helper ────────────────────────────────────────────────


def test_k_agent_ctx_role_uses_new_project_format() -> None:
    from app.adapters.redis_client import k_agent_ctx_role

    assert k_agent_ctx_role("proj-A", "engineer") == "agent:ctx:proj:proj-A:engineer"
