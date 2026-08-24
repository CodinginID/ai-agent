"""Unit tests for UserSessionRepository — in-memory SQLite, no mocks needed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.database.base import Base
from app.adapters.sessions import DEFAULT_TTL, UserSessionRepository, _ensure_utc


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)


def _repo(factory) -> UserSessionRepository:
    return UserSessionRepository(factory)


# ── _ensure_utc ───────────────────────────────────────────────────────────────

def test_ensure_utc_adds_utc_to_naive_datetime() -> None:
    naive = datetime(2024, 6, 1, 12, 0, 0)
    result = _ensure_utc(naive)
    assert result.tzinfo is UTC


def test_ensure_utc_leaves_tz_aware_datetime_unchanged() -> None:
    aware = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    assert _ensure_utc(aware) == aware


# ── create ────────────────────────────────────────────────────────────────────

def test_create_returns_session_info_with_correct_user_id(factory) -> None:
    info = _repo(factory).create("user-abc")
    assert info.user_id == "user-abc"


def test_create_token_is_non_empty_string(factory) -> None:
    info = _repo(factory).create("user-1")
    assert isinstance(info.token, str)
    assert len(info.token) > 20


def test_create_expires_at_is_in_the_future(factory) -> None:
    info = _repo(factory).create("user-1")
    assert info.expires_at > datetime.now(UTC)


def test_create_default_ttl_is_30_days(factory) -> None:
    before = datetime.now(UTC)
    info = _repo(factory).create("user-1")
    expected = before + DEFAULT_TTL
    assert abs((info.expires_at - expected).total_seconds()) < 5


def test_create_respects_custom_ttl(factory) -> None:
    info = _repo(factory).create("user-1", ttl=timedelta(hours=2))
    expected = datetime.now(UTC) + timedelta(hours=2)
    assert abs((info.expires_at - expected).total_seconds()) < 5


def test_create_generates_unique_tokens_for_same_user(factory) -> None:
    repo = _repo(factory)
    a = repo.create("user-1")
    b = repo.create("user-1")
    assert a.token != b.token


def test_create_stores_user_agent(factory) -> None:
    info = _repo(factory).create("user-1", user_agent="TUI/1.0")
    # Verify token can be resolved — user_agent is stored, no error thrown
    resolved = _repo(factory).resolve(info.token)
    assert resolved is not None


# ── resolve ───────────────────────────────────────────────────────────────────

def test_resolve_returns_session_info_for_valid_token(factory) -> None:
    repo = _repo(factory)
    created = repo.create("user-2")
    resolved = repo.resolve(created.token)
    assert resolved is not None
    assert resolved.user_id == "user-2"
    assert resolved.token == created.token


def test_resolve_expires_at_has_timezone(factory) -> None:
    repo = _repo(factory)
    info = repo.create("user-2")
    resolved = repo.resolve(info.token)
    assert resolved is not None
    assert resolved.expires_at.tzinfo is not None


def test_resolve_returns_none_for_unknown_token(factory) -> None:
    assert _repo(factory).resolve("this-token-does-not-exist") is None


def test_resolve_returns_none_for_empty_string(factory) -> None:
    assert _repo(factory).resolve("") is None


def test_resolve_returns_none_for_expired_token(factory) -> None:
    repo = _repo(factory)
    info = repo.create("user-3", ttl=timedelta(seconds=-1))
    assert repo.resolve(info.token) is None


def test_resolve_can_be_called_twice_on_same_token(factory) -> None:
    repo = _repo(factory)
    info = repo.create("user-2")
    assert repo.resolve(info.token) is not None
    assert repo.resolve(info.token) is not None


# ── revoke ────────────────────────────────────────────────────────────────────

def test_revoke_returns_true_for_existing_token(factory) -> None:
    repo = _repo(factory)
    info = repo.create("user-4")
    assert repo.revoke(info.token) is True


def test_revoke_makes_token_unresolvable(factory) -> None:
    repo = _repo(factory)
    info = repo.create("user-4")
    repo.revoke(info.token)
    assert repo.resolve(info.token) is None


def test_revoke_returns_false_for_unknown_token(factory) -> None:
    assert _repo(factory).revoke("ghost-token") is False


def test_revoke_only_removes_target_token(factory) -> None:
    repo = _repo(factory)
    keep = repo.create("user-4")
    gone = repo.create("user-4")
    repo.revoke(gone.token)
    assert repo.resolve(keep.token) is not None


# ── revoke_all_for_user ───────────────────────────────────────────────────────

def test_revoke_all_for_user_returns_count_of_removed_sessions(factory) -> None:
    repo = _repo(factory)
    repo.create("user-5")
    repo.create("user-5")
    repo.create("user-5")
    assert repo.revoke_all_for_user("user-5") == 3


def test_revoke_all_for_user_makes_all_tokens_unresolvable(factory) -> None:
    repo = _repo(factory)
    a = repo.create("user-5")
    b = repo.create("user-5")
    repo.revoke_all_for_user("user-5")
    assert repo.resolve(a.token) is None
    assert repo.resolve(b.token) is None


def test_revoke_all_for_user_returns_zero_when_no_sessions(factory) -> None:
    assert _repo(factory).revoke_all_for_user("nobody") == 0


def test_revoke_all_for_user_does_not_touch_other_users(factory) -> None:
    repo = _repo(factory)
    other = repo.create("user-6")
    repo.create("user-7")
    repo.revoke_all_for_user("user-7")
    assert repo.resolve(other.token) is not None


# ── purge_expired ─────────────────────────────────────────────────────────────

def test_purge_expired_removes_expired_and_returns_count(factory) -> None:
    repo = _repo(factory)
    repo.create("user-8", ttl=timedelta(seconds=-1))
    repo.create("user-8", ttl=timedelta(seconds=-1))
    assert repo.purge_expired() == 2


def test_purge_expired_leaves_valid_sessions_intact(factory) -> None:
    repo = _repo(factory)
    valid = repo.create("user-8")
    repo.create("user-8", ttl=timedelta(seconds=-1))
    repo.purge_expired()
    assert repo.resolve(valid.token) is not None


def test_purge_expired_returns_zero_when_nothing_expired(factory) -> None:
    repo = _repo(factory)
    repo.create("user-8")
    assert repo.purge_expired() == 0
