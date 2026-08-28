"""Port untuk Web Push notification — notifikasi browser saat approval/task selesai.

Konsep sama seperti port lain (task_events, github_issues): domain/interfaces
tergantung pada Protocol ini, bukan implementasi konkret (``WebPushAdapter``).
``NullPush`` jadi default no-op supaya kode yang butuh push tetap jalan tanpa
VAPID key di-set (dev/test).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class PushSubscription:
    """Subscription browser (hasil ``PushManager.subscribe()``)."""

    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class PushMessage:
    """Payload notifikasi yang dikirim ke service worker klien."""

    title: str
    body: str
    tag: str
    url: str = "/"
    kind: str = "info"
    data: dict[str, str] = field(default_factory=dict)


class PushPort(Protocol):
    async def subscribe(self, user_id: str, sub: PushSubscription) -> None: ...

    async def unsubscribe(self, user_id: str, endpoint: str) -> None: ...

    async def notify(self, user_id: str, msg: PushMessage) -> int:
        """Kirim notifikasi ke semua subscription user. Return jumlah terkirim."""
        ...

    def is_configured(self) -> bool: ...


class NullPush:
    """No-op — dipakai saat VAPID key belum di-set (dev/test)."""

    async def subscribe(self, user_id: str, sub: PushSubscription) -> None:
        return None

    async def unsubscribe(self, user_id: str, endpoint: str) -> None:
        return None

    async def notify(self, user_id: str, msg: PushMessage) -> int:
        return 0

    def is_configured(self) -> bool:
        return False
