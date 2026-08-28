"""_mirror_to_room pushes a Web Push notification on APPROVAL_REQUIRED.

Uses the same monkeypatch pattern as test_room.py: real ``_mirror_to_room``,
fake ``build_push`` injected via ``app.composition.build_push`` (the lazy
import inside ``_push_approval_notice``), asserted after letting the
fire-and-forget asyncio task run.
"""

from __future__ import annotations

import asyncio

import app.composition as composition_mod
import app.interfaces.chat as chat_mod
from app.domain.messaging import ChatEvent
from app.ports.push import PushMessage, PushSubscription


class _FakePush:
    def __init__(self) -> None:
        self.notified: list[tuple[str, PushMessage]] = []

    async def subscribe(self, user_id: str, sub: PushSubscription) -> None:
        return None

    async def unsubscribe(self, user_id: str, endpoint: str) -> None:
        return None

    async def notify(self, user_id: str, msg: PushMessage) -> int:
        self.notified.append((user_id, msg))
        return 1

    def is_configured(self) -> bool:
        return True


def test_mirror_to_room_pushes_approval_notice(monkeypatch) -> None:
    fake = _FakePush()
    monkeypatch.setattr(composition_mod, "build_push", lambda: fake)

    async def go() -> None:
        ev = ChatEvent.approval_required("plan-123", "hapus 5 file lama")
        chat_mod._mirror_to_room(ev, "user-7")
        await asyncio.sleep(0)  # let the fire-and-forget push task run

    asyncio.run(go())

    assert len(fake.notified) == 1
    user_id, msg = fake.notified[0]
    assert user_id == "user-7"
    assert msg.kind == "approval"
    assert msg.data == {"plan_id": "plan-123"}
    assert msg.tag == "approval-plan-123"


def test_mirror_to_room_without_user_id_does_not_raise(monkeypatch) -> None:
    """Existing callers (e.g. tests) may omit user_id — default keeps them green."""
    fake = _FakePush()
    monkeypatch.setattr(composition_mod, "build_push", lambda: fake)

    async def go() -> None:
        chat_mod._mirror_to_room(ChatEvent.final("done"))
        await asyncio.sleep(0)

    asyncio.run(go())  # must not raise
