"""Smoke tests for pure domain entities — no external dependencies."""

from app.domain.accounts import DeviceIdentity, TenantIdentity
from app.domain.messaging import ChatEventType, MessageContext


def test_tenant_identity_immutable() -> None:
    tenant = TenantIdentity(
        user_id="u1", telegram_account_id="acc1", telegram_user_id=123
    )
    assert tenant.user_id == "u1"
    assert tenant.telegram_user_id == 123


def test_device_identity_fields() -> None:
    device = DeviceIdentity(device_id="d1", user_id="u1", name="vps-01")
    assert device.device_id == "d1"
    assert device.name == "vps-01"


def test_chat_event_type_values() -> None:
    assert ChatEventType.FINAL == "final"
    assert ChatEventType.ERROR == "error"


def test_message_context_fields() -> None:
    from pathlib import Path

    ctx = MessageContext(
        user_id="u1",
        conversation_id="chat-123",
        project_id="proj-1",
        project_root=Path("/workspace"),
        project_name="my-project",
    )
    assert ctx.user_id == "u1"
    assert ctx.conversation_id == "chat-123"
    assert ctx.telegram_user_id is None
