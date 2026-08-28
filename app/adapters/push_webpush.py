"""Web Push adapter — kirim notifikasi browser via VAPID (RFC 8292).

``RedisPushSubscriptionStore`` menyimpan subscription per user di hash Redis
(``k_push_subs(user_id)``, field=endpoint, value=JSON subscription). Kalau
push gagal terkirim dengan status 404/410 (endpoint kedaluwarsa/dihapus
browser), subscription itu otomatis dibuang dari store.

``WebPushAdapter`` implement ``PushPort`` — best-effort: kegagalan kirim
(selain 404/410) hanya di-log, tidak pernah raise ke pemanggil (task
observer / chat mirror tidak boleh terganggu gara-gara push gagal).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol, cast

from app.adapters.redis_client import get_client, k_push_subs
from app.ports.push import PushMessage, PushSubscription

logger = logging.getLogger(__name__)


class _RedisLike(Protocol):
    async def hset(self, name: str, key: str, value: str) -> Any: ...
    async def hgetall(self, name: str) -> dict[str, str]: ...
    async def hdel(self, name: str, *keys: str) -> Any: ...


class RedisPushSubscriptionStore:
    """CRUD subscription Web Push di Redis hash — satu hash per user."""

    def __init__(self, redis_client: _RedisLike | None = None) -> None:
        self._client = redis_client

    def _redis(self) -> _RedisLike:
        if self._client is not None:
            return self._client
        return cast("_RedisLike", get_client())

    async def add(self, user_id: str, sub: PushSubscription) -> None:
        payload = json.dumps(
            {"endpoint": sub.endpoint, "p256dh": sub.p256dh, "auth": sub.auth}
        )
        await self._redis().hset(k_push_subs(user_id), sub.endpoint, payload)

    async def remove(self, user_id: str, endpoint: str) -> None:
        await self._redis().hdel(k_push_subs(user_id), endpoint)

    async def list(self, user_id: str) -> list[PushSubscription]:
        raw = await self._redis().hgetall(k_push_subs(user_id))
        out: list[PushSubscription] = []
        for value in raw.values():
            try:
                d = json.loads(value)
                out.append(
                    PushSubscription(
                        endpoint=d["endpoint"], p256dh=d["p256dh"], auth=d["auth"]
                    )
                )
            except (ValueError, KeyError, TypeError):
                logger.warning("push subscription korup, dilewati")
        return out


def _default_sender() -> Any:
    """Import pywebpush lazily supaya adapter tetap importable tanpa dependency
    ter-install (mis. saat test hanya butuh store), dan supaya test bisa inject
    ``sender`` fake tanpa mem-patch modul ``pywebpush``."""
    from pywebpush import webpush

    return webpush


class WebPushAdapter:
    """``PushPort`` konkret — kirim via VAPID ke setiap subscription user."""

    def __init__(
        self,
        store: RedisPushSubscriptionStore,
        vapid_private_key: str,
        vapid_subject: str,
        sender: Any = None,
    ) -> None:
        self._store = store
        self._vapid_private_key = vapid_private_key
        self._vapid_subject = vapid_subject
        self._sender = sender if sender is not None else _default_sender()

    def is_configured(self) -> bool:
        return bool(self._vapid_private_key)

    async def subscribe(self, user_id: str, sub: PushSubscription) -> None:
        await self._store.add(user_id, sub)

    async def unsubscribe(self, user_id: str, endpoint: str) -> None:
        await self._store.remove(user_id, endpoint)

    async def notify(self, user_id: str, msg: PushMessage) -> int:
        if not self.is_configured():
            return 0

        subs = await self._store.list(user_id)
        if not subs:
            return 0

        payload = json.dumps(
            {
                "title": msg.title,
                "body": msg.body,
                "tag": msg.tag,
                "url": msg.url,
                "kind": msg.kind,
                "data": msg.data,
            }
        )

        delivered = 0
        for sub in subs:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            }
            try:
                # pywebpush.webpush = HTTP sinkron (requests) → jalankan di thread
                # supaya event loop (SSE chat / task runner) tidak terblokir.
                await asyncio.to_thread(
                    self._sender,
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=self._vapid_private_key,
                    vapid_claims={"sub": self._vapid_subject},
                    ttl=60,
                )
                delivered += 1
            except Exception as exc:  # pywebpush.WebPushException atau lainnya
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (404, 410):
                    await self._store.remove(user_id, sub.endpoint)
                    logger.info("push subscription kedaluwarsa, dihapus: %s", sub.endpoint)
                else:
                    logger.warning("push gagal terkirim: %s", exc)

        return delivered
