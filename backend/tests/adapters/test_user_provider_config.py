# tests/adapters/test_user_provider_config.py
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.database.models import Base, UserModel
from app.adapters.user_provider_config import UserProviderConfigRepository


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as s:
        s.add(UserModel(id="u1", email="a@b.c"))
        s.commit()
    return factory


def test_get_returns_none_when_unset(factory) -> None:
    assert UserProviderConfigRepository(factory).get("u1") is None


def test_set_then_get_roundtrip(factory) -> None:
    repo = UserProviderConfigRepository(factory)
    repo.set("u1", "anthropic", "claude-opus-4-8")
    assert repo.get("u1") == ("anthropic", "claude-opus-4-8")


def test_set_is_upsert(factory) -> None:
    repo = UserProviderConfigRepository(factory)
    repo.set("u1", "anthropic", "claude-opus-4-8")
    repo.set("u1", "ollama", None)
    assert repo.get("u1") == ("ollama", None)
