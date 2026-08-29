"""Roster adapter — CRUD nama/peran agen di Redis hash, satu hash per user.

``RedisRosterStore.list`` mengembalikan ``DEFAULT_ROSTER`` selama hash belum
pernah ditulis (user belum pernah mengubah roster-nya). Begitu ada mutasi
pertama (``upsert``/``delete``), hash di-seed dengan seluruh ``DEFAULT_ROSTER``
lebih dulu — supaya rename/hapus satu agen tidak diam-diam membuang 6 agen
default lain yang belum pernah disentuh user.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, cast

from app.adapters.redis_client import get_client, k_roster
from app.ports.roster import DEFAULT_ROSTER, RosterAgent

logger = logging.getLogger(__name__)


class _RedisLike(Protocol):
    async def hset(self, name: str, key: str, value: str) -> Any: ...
    async def hgetall(self, name: str) -> dict[str, str]: ...
    async def hdel(self, name: str, *keys: str) -> Any: ...


def _encode(agent: RosterAgent) -> str:
    return json.dumps({"id": agent.id, "name": agent.name, "role": agent.role})


def _decode(raw: str) -> RosterAgent | None:
    try:
        d = json.loads(raw)
        return RosterAgent(id=d["id"], name=d["name"], role=d["role"])
    except (ValueError, KeyError, TypeError):
        logger.warning("roster entry korup, dilewati")
        return None


class RedisRosterStore:
    """``RosterPort`` konkret — hash Redis (field=agent_id, value=JSON)."""

    def __init__(self, redis_client: _RedisLike | None = None) -> None:
        self._client = redis_client

    def _redis(self) -> _RedisLike:
        if self._client is not None:
            return self._client
        return cast("_RedisLike", get_client())

    async def list(self, user_id: str) -> list[RosterAgent]:
        raw = await self._redis().hgetall(k_roster(user_id))
        if not raw:
            return list(DEFAULT_ROSTER)
        agents = [_decode(v) for v in raw.values()]
        return [a for a in agents if a is not None]

    async def _seed_if_empty(self, user_id: str) -> None:
        existing = await self._redis().hgetall(k_roster(user_id))
        if existing:
            return
        redis = self._redis()
        for agent in DEFAULT_ROSTER:
            await redis.hset(k_roster(user_id), agent.id, _encode(agent))

    async def upsert(self, user_id: str, agent: RosterAgent) -> None:
        await self._seed_if_empty(user_id)
        await self._redis().hset(k_roster(user_id), agent.id, _encode(agent))

    async def delete(self, user_id: str, agent_id: str) -> bool:
        await self._seed_if_empty(user_id)
        n = await self._redis().hdel(k_roster(user_id), agent_id)
        return bool(n)
