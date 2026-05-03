import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.database import models
from app.adapters.database.base import Base
from app.adapters.database.repositories import ControlPlaneRepository, DatabaseConflictError
from app.domain.tokens import hash_device_token

_MODELS_MODULE = models


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return session_factory()


def test_resolve_by_telegram_user_id_returns_tenant_identity() -> None:
    session = make_session()
    repo = ControlPlaneRepository(session)
    user = repo.create_user(display_name="Ali")
    account = repo.link_telegram_account(
        user_id=user.id,
        telegram_user_id=123456,
        username="ali",
    )

    tenant = repo.resolve_by_telegram_user_id(123456)

    assert tenant is not None
    assert tenant.user_id == user.id
    assert tenant.telegram_account_id == account.id
    assert tenant.telegram_user_id == 123456


def test_link_telegram_account_rejects_duplicate_telegram_user_id() -> None:
    session = make_session()
    repo = ControlPlaneRepository(session)
    first_user = repo.create_user(display_name="First")
    second_user = repo.create_user(display_name="Second")
    repo.link_telegram_account(user_id=first_user.id, telegram_user_id=123456)

    with pytest.raises(DatabaseConflictError):
        repo.link_telegram_account(user_id=second_user.id, telegram_user_id=123456)


def test_register_device_scopes_device_name_to_user() -> None:
    session = make_session()
    repo = ControlPlaneRepository(session)
    first_user = repo.create_user(display_name="First")
    second_user = repo.create_user(display_name="Second")

    first_device = repo.register_device(
        user_id=first_user.id,
        name="my-vps",
        device_token_hash=hash_device_token("first-token"),
    )
    second_device = repo.register_device(
        user_id=second_user.id,
        name="my-vps",
        device_token_hash=hash_device_token("second-token"),
    )

    assert first_device.user_id == first_user.id
    assert second_device.user_id == second_user.id
    assert first_device.device_id != second_device.device_id


def test_register_device_rejects_duplicate_name_for_same_user() -> None:
    session = make_session()
    repo = ControlPlaneRepository(session)
    user = repo.create_user(display_name="Ali")
    repo.register_device(
        user_id=user.id,
        name="my-vps",
        device_token_hash=hash_device_token("first-token"),
    )

    with pytest.raises(DatabaseConflictError):
        repo.register_device(
            user_id=user.id,
            name="my-vps",
            device_token_hash=hash_device_token("second-token"),
        )


def test_upsert_agent_integration_marks_ready_when_install_enabled_and_probe_ok() -> None:
    session = make_session()
    repo = ControlPlaneRepository(session)
    user = repo.create_user(display_name="Ali")
    device = repo.register_device(
        user_id=user.id,
        name="my-vps",
        device_token_hash=hash_device_token("device-token"),
    )

    integration = repo.upsert_agent_integration(
        device_id=device.device_id,
        agent_id="codex",
        display_name="Codex",
        provider="openai",
        executable="codex",
        installed=True,
        enabled=True,
        probe_ok=True,
        status="ready",
        capabilities={"role": "engineer"},
    )

    assert integration.ready is True
    assert integration.capabilities == {"role": "engineer"}
