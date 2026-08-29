"""Unit tests -- RedisRosterStore (in-memory fake Redis hash, no jaringan nyata)."""

from __future__ import annotations

from app.adapters.roster_redis import RedisRosterStore
from app.ports.roster import DEFAULT_ROSTER, RosterAgent


class FakeRedisHash:
    """Stand-in minimal untuk redis async client -- cukup hset/hgetall/hdel."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, str]] = {}

    async def hset(self, name: str, key: str, value: str) -> int:
        self._data.setdefault(name, {})[key] = value
        return 1

    async def hgetall(self, name: str) -> dict[str, str]:
        return dict(self._data.get(name, {}))

    async def hdel(self, name: str, *keys: str) -> int:
        bucket = self._data.get(name, {})
        n = 0
        for k in keys:
            if k in bucket:
                del bucket[k]
                n += 1
        return n


def _store() -> tuple[RedisRosterStore, FakeRedisHash]:
    redis = FakeRedisHash()
    return RedisRosterStore(redis), redis


async def test_list_returns_default_roster_when_empty() -> None:
    store, _redis = _store()
    agents = await store.list("user-1")
    assert agents == list(DEFAULT_ROSTER)


async def test_upsert_then_list_seeds_defaults_and_applies_change() -> None:
    store, _redis = _store()
    await store.upsert("user-1", RosterAgent(id="octo", name="Kapten", role="manager"))

    agents = await store.list("user-1")
    by_id = {a.id: a for a in agents}
    assert len(agents) == len(DEFAULT_ROSTER)
    assert by_id["octo"].name == "Kapten"
    # agen lain tetap ada (bukan cuma "octo") -- seed default terjadi di upsert pertama.
    assert by_id["nadia"].name == "Nadia"


async def test_upsert_adds_new_agent() -> None:
    store, _redis = _store()
    await store.upsert("user-1", RosterAgent(id="baru", name="Agen Baru", role="coder"))

    agents = await store.list("user-1")
    by_id = {a.id: a for a in agents}
    assert len(agents) == len(DEFAULT_ROSTER) + 1
    assert by_id["baru"].role == "coder"


async def test_delete_removes_agent() -> None:
    store, _redis = _store()
    await store.upsert("user-1", RosterAgent(id="nadia", name="Nadia Baru", role="coder"))

    ok = await store.delete("user-1", "nadia")
    assert ok is True
    agents = await store.list("user-1")
    assert "nadia" not in {a.id for a in agents}


async def test_delete_unknown_agent_returns_false() -> None:
    store, _redis = _store()
    assert await store.delete("user-1", "nobody") is False


async def test_roster_scoped_per_user() -> None:
    store, _redis = _store()
    await store.upsert("user-1", RosterAgent(id="octo", name="Kapten", role="manager"))

    agents_u2 = await store.list("user-2")
    assert agents_u2 == list(DEFAULT_ROSTER)
