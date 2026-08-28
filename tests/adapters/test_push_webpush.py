"""Unit tests -- RedisPushSubscriptionStore + WebPushAdapter (in-memory fake Redis).

Tidak ada real Redis / network: store pakai fake hash (hset/hgetall/hdel), dan
adapter dites lewat ``sender`` callable palsu (bukan ``pywebpush.webpush``
asli) supaya deterministik & tidak butuh koneksi jaringan.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.adapters.push_webpush import RedisPushSubscriptionStore, WebPushAdapter
from app.ports.push import NullPush, PushMessage, PushSubscription


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


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeWebPushError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"push failed {status_code}")
        self.response = _FakeResponse(status_code)


def _sub(n: int) -> PushSubscription:
    return PushSubscription(endpoint=f"https://push.example/{n}", p256dh="p256", auth="auth")


@pytest.fixture
def redis() -> FakeRedisHash:
    return FakeRedisHash()


@pytest.fixture
def store(redis: FakeRedisHash) -> RedisPushSubscriptionStore:
    return RedisPushSubscriptionStore(redis)


# -- store --------------------------------------------------------------------


async def test_store_add_list_remove(store: RedisPushSubscriptionStore) -> None:
    await store.add("user-1", _sub(1))
    await store.add("user-1", _sub(2))

    subs = await store.list("user-1")
    assert {s.endpoint for s in subs} == {"https://push.example/1", "https://push.example/2"}

    await store.remove("user-1", "https://push.example/1")
    subs2 = await store.list("user-1")
    assert [s.endpoint for s in subs2] == ["https://push.example/2"]


async def test_store_list_empty_for_unknown_user(store: RedisPushSubscriptionStore) -> None:
    assert await store.list("nobody") == []


# -- adapter --------------------------------------------------------------------


def _msg() -> PushMessage:
    return PushMessage(title="Octopus", body="hi", tag="t1", url="/", kind="task")


async def test_notify_delivers_to_all_subscriptions(store: RedisPushSubscriptionStore) -> None:
    await store.add("user-1", _sub(1))
    await store.add("user-1", _sub(2))
    calls: list[dict[str, Any]] = []

    def sender(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "ok"

    adapter = WebPushAdapter(store, vapid_private_key="priv", vapid_subject="mailto:a@b.com", sender=sender)
    delivered = await adapter.notify("user-1", _msg())

    assert delivered == 2
    assert len(calls) == 2
    assert calls[0]["vapid_claims"] == {"sub": "mailto:a@b.com"}


async def test_notify_removes_subscription_on_410(store: RedisPushSubscriptionStore) -> None:
    await store.add("user-1", _sub(1))
    await store.add("user-1", _sub(2))

    def sender(**kwargs: Any) -> str:
        if kwargs["subscription_info"]["endpoint"].endswith("/1"):
            raise FakeWebPushError(410)
        return "ok"

    adapter = WebPushAdapter(store, vapid_private_key="priv", vapid_subject="mailto:a@b.com", sender=sender)
    delivered = await adapter.notify("user-1", _msg())

    assert delivered == 1
    remaining = await store.list("user-1")
    assert [s.endpoint for s in remaining] == ["https://push.example/2"]


async def test_notify_swallows_generic_errors(store: RedisPushSubscriptionStore) -> None:
    await store.add("user-1", _sub(1))

    def sender(**kwargs: Any) -> str:
        raise RuntimeError("network boom")

    adapter = WebPushAdapter(store, vapid_private_key="priv", vapid_subject="mailto:a@b.com", sender=sender)
    delivered = await adapter.notify("user-1", _msg())

    assert delivered == 0
    # generic errors don't remove the subscription (only 404/410 do)
    assert len(await store.list("user-1")) == 1


async def test_notify_noop_when_not_configured(store: RedisPushSubscriptionStore) -> None:
    await store.add("user-1", _sub(1))
    adapter = WebPushAdapter(store, vapid_private_key="", vapid_subject="mailto:a@b.com", sender=lambda **_: "ok")
    assert adapter.is_configured() is False
    assert await adapter.notify("user-1", _msg()) == 0


async def test_null_push_returns_zero() -> None:
    push = NullPush()
    assert push.is_configured() is False
    assert await push.notify("user-1", _msg()) == 0
    await push.subscribe("user-1", _sub(1))
    await push.unsubscribe("user-1", "https://push.example/1")
