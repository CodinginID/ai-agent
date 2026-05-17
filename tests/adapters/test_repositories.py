"""Unit tests for ControlPlaneRepository — new query methods added for issue #3."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.database.models import Base, UserModel
from app.adapters.database.repositories import ControlPlaneRepository


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


@pytest.fixture()
def repo_with_user(session):
    user = UserModel(display_name="Alice", email="alice@example.com")
    session.add(user)
    session.flush()
    repo = ControlPlaneRepository(session)
    return repo, user.id


# ── find_or_create_device_by_name ─────────────────────────────────────────────

def test_find_or_create_creates_new_device(repo_with_user) -> None:
    repo, user_id = repo_with_user
    device = repo.find_or_create_device_by_name(user_id, "macbook-pro")
    assert device.id is not None
    assert device.name == "macbook-pro"
    assert device.user_id == user_id


def test_find_or_create_returns_existing_on_second_call(repo_with_user) -> None:
    repo, user_id = repo_with_user
    d1 = repo.find_or_create_device_by_name(user_id, "ws-machine")
    d2 = repo.find_or_create_device_by_name(user_id, "ws-machine")
    assert d1.id == d2.id


def test_find_or_create_different_names_produce_different_devices(repo_with_user) -> None:
    repo, user_id = repo_with_user
    d1 = repo.find_or_create_device_by_name(user_id, "laptop")
    d2 = repo.find_or_create_device_by_name(user_id, "desktop")
    assert d1.id != d2.id


def test_find_or_create_token_hash_is_deterministic(repo_with_user) -> None:
    import hashlib
    repo, user_id = repo_with_user
    device = repo.find_or_create_device_by_name(user_id, "srv")
    expected = hashlib.sha256(f"ws:{user_id}:srv".encode()).hexdigest()[:64]
    assert device.device_token_hash == expected


# ── list_devices ──────────────────────────────────────────────────────────────

def test_list_devices_returns_empty_for_new_user(repo_with_user) -> None:
    repo, user_id = repo_with_user
    assert repo.list_devices(user_id) == []


def test_list_devices_returns_all_created(repo_with_user) -> None:
    repo, user_id = repo_with_user
    repo.find_or_create_device_by_name(user_id, "a")
    repo.find_or_create_device_by_name(user_id, "b")
    devices = repo.list_devices(user_id)
    assert len(devices) == 2
    names = {d.name for d in devices}
    assert names == {"a", "b"}


def test_list_devices_does_not_cross_users(session) -> None:
    u1 = UserModel(display_name="U1", email="u1@example.com")
    u2 = UserModel(display_name="U2", email="u2@example.com")
    session.add_all([u1, u2])
    session.flush()
    repo = ControlPlaneRepository(session)
    repo.find_or_create_device_by_name(u1.id, "shared-name")
    assert repo.list_devices(u2.id) == []


# ── get_device ────────────────────────────────────────────────────────────────

def test_get_device_returns_device(repo_with_user) -> None:
    repo, user_id = repo_with_user
    created = repo.find_or_create_device_by_name(user_id, "mypc")
    fetched = repo.get_device(created.id, user_id)
    assert fetched is not None
    assert fetched.id == created.id


def test_get_device_returns_none_for_wrong_user(session) -> None:
    u1 = UserModel(display_name="U1", email="u1@x.com")
    u2 = UserModel(display_name="U2", email="u2@x.com")
    session.add_all([u1, u2])
    session.flush()
    repo = ControlPlaneRepository(session)
    device = repo.find_or_create_device_by_name(u1.id, "machine")
    assert repo.get_device(device.id, u2.id) is None


def test_get_device_returns_none_for_unknown_id(repo_with_user) -> None:
    repo, user_id = repo_with_user
    assert repo.get_device("nonexistent-id", user_id) is None


# ── list_agent_integrations ───────────────────────────────────────────────────

def test_list_agent_integrations_empty_initially(repo_with_user) -> None:
    repo, user_id = repo_with_user
    device = repo.find_or_create_device_by_name(user_id, "dev")
    assert repo.list_agent_integrations(device.id) == []


def test_list_agent_integrations_returns_upserted(repo_with_user) -> None:
    repo, user_id = repo_with_user
    device = repo.find_or_create_device_by_name(user_id, "dev")
    repo.upsert_agent_integration(
        device_id=device.id,
        agent_id="claude",
        display_name="Claude",
        provider="anthropic",
        executable="/usr/local/bin/claude",
        installed=True,
        enabled=False,
        probe_ok=True,
        status="installed",
    )
    integrations = repo.list_agent_integrations(device.id)
    assert len(integrations) == 1
    assert integrations[0].agent_id == "claude"


def test_list_agent_integrations_does_not_cross_devices(repo_with_user) -> None:
    repo, user_id = repo_with_user
    d1 = repo.find_or_create_device_by_name(user_id, "dev1")
    d2 = repo.find_or_create_device_by_name(user_id, "dev2")
    repo.upsert_agent_integration(
        device_id=d1.id,
        agent_id="codex",
        display_name="Codex",
        provider="openai",
        executable=None,
        installed=False,
        enabled=False,
        probe_ok=False,
        status="not_installed",
    )
    assert repo.list_agent_integrations(d2.id) == []


# ── Project / active-project helpers ──────────────────────────────────────────


def test_list_user_projects_empty_initially(repo_with_user) -> None:
    repo, user_id = repo_with_user
    assert repo.list_user_projects(user_id) == []


def test_list_user_projects_returns_created(repo_with_user) -> None:
    repo, user_id = repo_with_user
    repo.create_project(user_id, "payment-svc", "/srv/payment")
    repo.create_project(user_id, "auth-svc", "/srv/auth")
    names = sorted(p.name for p in repo.list_user_projects(user_id))
    assert names == ["auth-svc", "payment-svc"]


def test_list_user_projects_does_not_cross_users(repo_with_user, session) -> None:
    repo, user_id = repo_with_user
    other = UserModel(display_name="Bob", email="bob@example.com")
    session.add(other)
    session.flush()
    repo.create_project(user_id, "alice-proj", ".")
    repo.create_project(other.id, "bob-proj", ".")
    alice_names = [p.name for p in repo.list_user_projects(user_id)]
    bob_names = [p.name for p in repo.list_user_projects(other.id)]
    assert alice_names == ["alice-proj"]
    assert bob_names == ["bob-proj"]


def test_get_project_returns_project_when_owned(repo_with_user) -> None:
    repo, user_id = repo_with_user
    created = repo.create_project(user_id, "myproj", ".")
    fetched = repo.get_project(created.id, user_id)
    assert fetched is not None
    assert fetched.id == created.id


def test_get_project_returns_none_for_other_user(repo_with_user, session) -> None:
    repo, user_id = repo_with_user
    other = UserModel(display_name="Bob", email="bob@example.com")
    session.add(other)
    session.flush()
    project = repo.create_project(user_id, "mine", ".")
    assert repo.get_project(project.id, other.id) is None


def test_get_or_create_default_project_creates_when_absent(repo_with_user) -> None:
    repo, user_id = repo_with_user
    assert repo.list_user_projects(user_id) == []
    project = repo.get_or_create_default_project(user_id)
    assert project.name == "default"
    assert project.user_id == user_id
    assert len(repo.list_user_projects(user_id)) == 1


def test_get_or_create_default_project_idempotent(repo_with_user) -> None:
    repo, user_id = repo_with_user
    p1 = repo.get_or_create_default_project(user_id)
    p2 = repo.get_or_create_default_project(user_id)
    assert p1.id == p2.id
    assert len(repo.list_user_projects(user_id)) == 1


def test_get_or_create_default_returns_existing_first_project(repo_with_user) -> None:
    """Kalau user sudah punya project, jangan auto-bikin 'default' baru."""
    repo, user_id = repo_with_user
    custom = repo.create_project(user_id, "my-custom", ".")
    result = repo.get_or_create_default_project(user_id)
    assert result.id == custom.id


def test_set_device_active_project_updates_field(repo_with_user) -> None:
    repo, user_id = repo_with_user
    device = repo.find_or_create_device_by_name(user_id, "laptop")
    project = repo.create_project(user_id, "payment", ".")
    assert device.active_project_id is None
    updated = repo.set_device_active_project(device.id, user_id, project.id)
    assert updated.active_project_id == project.id


def test_set_device_active_project_rejects_unknown_device(repo_with_user) -> None:
    from app.adapters.database.repositories import DatabaseConflictError
    repo, user_id = repo_with_user
    project = repo.create_project(user_id, "x", ".")
    with pytest.raises(DatabaseConflictError):
        repo.set_device_active_project("ghost", user_id, project.id)


def test_set_device_active_project_rejects_cross_user_project(
    repo_with_user, session
) -> None:
    """User tidak boleh assign project milik user lain ke device-nya."""
    from app.adapters.database.repositories import DatabaseConflictError
    repo, user_id = repo_with_user
    device = repo.find_or_create_device_by_name(user_id, "laptop")

    other = UserModel(display_name="Bob", email="bob@example.com")
    session.add(other)
    session.flush()
    other_project = repo.create_project(other.id, "secret", ".")

    with pytest.raises(DatabaseConflictError):
        repo.set_device_active_project(device.id, user_id, other_project.id)


def test_resolve_device_project_id_returns_none_initially(repo_with_user) -> None:
    repo, user_id = repo_with_user
    device = repo.find_or_create_device_by_name(user_id, "laptop")
    assert repo.resolve_device_project_id(device.id, user_id) is None


def test_resolve_device_project_id_returns_set_id(repo_with_user) -> None:
    repo, user_id = repo_with_user
    device = repo.find_or_create_device_by_name(user_id, "laptop")
    project = repo.create_project(user_id, "p", ".")
    repo.set_device_active_project(device.id, user_id, project.id)
    assert repo.resolve_device_project_id(device.id, user_id) == project.id


def test_resolve_device_project_id_none_for_unknown_device(repo_with_user) -> None:
    repo, user_id = repo_with_user
    assert repo.resolve_device_project_id("ghost", user_id) is None
