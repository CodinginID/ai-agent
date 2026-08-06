"""Repository tests untuk Skill CRUD pada ``ControlPlaneRepository``."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.database.models import Base, UserModel
from app.adapters.database.repositories import (
    ControlPlaneRepository,
    DatabaseConflictError,
)
from app.domain.skills import SkillValidationError


def _valid_skill(name: str = "skill-a") -> dict[str, Any]:
    return {
        "name": name,
        "steps": [
            {"name": "design", "role": "architect"},
            {"name": "build", "role": "engineer", "depends_on": ["design"]},
        ],
    }


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


@pytest.fixture()
def repo_user_project(session):
    user = UserModel(display_name="Alice", email="alice@x.com")
    session.add(user)
    session.flush()
    repo = ControlPlaneRepository(session)
    project = repo.create_project(user.id, "myproj", ".")
    return repo, user.id, project.id


# ── create_skill ─────────────────────────────────────────────────────────────


def test_create_skill_stores_definition(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    row = repo.create_skill(project_id, user_id, _valid_skill("alpha"))
    assert row.id is not None
    assert row.name == "alpha"
    assert row.project_id == project_id
    assert isinstance(row.definition, dict)
    assert row.definition["name"] == "alpha"
    assert len(row.definition["steps"]) == 2


def test_create_skill_rejects_invalid_definition(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    bad = {"name": "broken", "steps": [{"name": "x", "role": "wizard"}]}
    with pytest.raises(SkillValidationError):
        repo.create_skill(project_id, user_id, bad)


def test_create_skill_rejects_duplicate_name_in_same_project(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    repo.create_skill(project_id, user_id, _valid_skill("dup"))
    with pytest.raises(DatabaseConflictError, match="sudah ada"):
        repo.create_skill(project_id, user_id, _valid_skill("dup"))


def test_create_skill_rejects_for_other_user_project(repo_user_project, session) -> None:
    repo, _user_id, project_id = repo_user_project
    other = UserModel(display_name="Bob", email="bob@x.com")
    session.add(other)
    session.flush()
    with pytest.raises(DatabaseConflictError):
        repo.create_skill(project_id, other.id, _valid_skill("x"))


# ── list / get ───────────────────────────────────────────────────────────────


def test_list_skills_returns_created(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    repo.create_skill(project_id, user_id, _valid_skill("a"))
    repo.create_skill(project_id, user_id, _valid_skill("b"))
    names = sorted(s.name for s in repo.list_project_skills(project_id, user_id))
    assert names == ["a", "b"]


def test_list_skills_empty_for_unknown_project(repo_user_project) -> None:
    repo, user_id, _ = repo_user_project
    assert repo.list_project_skills("ghost", user_id) == []


def test_list_skills_isolates_users(repo_user_project, session) -> None:
    repo, user_id, project_id = repo_user_project
    repo.create_skill(project_id, user_id, _valid_skill("a"))
    other = UserModel(display_name="Bob", email="bob@x.com")
    session.add(other)
    session.flush()
    assert repo.list_project_skills(project_id, other.id) == []


def test_get_skill_by_id_for_owner(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    created = repo.create_skill(project_id, user_id, _valid_skill("a"))
    got = repo.get_skill(created.id, user_id)
    assert got is not None and got.name == "a"


def test_get_skill_by_id_returns_none_for_other_user(repo_user_project, session) -> None:
    repo, user_id, project_id = repo_user_project
    created = repo.create_skill(project_id, user_id, _valid_skill("a"))
    other = UserModel(display_name="Bob", email="bob@x.com")
    session.add(other)
    session.flush()
    assert repo.get_skill(created.id, other.id) is None


def test_get_skill_by_name(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    repo.create_skill(project_id, user_id, _valid_skill("named"))
    got = repo.get_skill_by_name(project_id, "named", user_id)
    assert got is not None and got.name == "named"


# ── update_skill ─────────────────────────────────────────────────────────────


def test_update_skill_replaces_definition(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    row = repo.create_skill(project_id, user_id, _valid_skill("orig"))
    new_def = _valid_skill("orig")
    new_def["description"] = "updated"
    updated = repo.update_skill(row.id, user_id, new_def)
    assert updated.description == "updated"


def test_update_skill_rename_collision_rejected(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    repo.create_skill(project_id, user_id, _valid_skill("a"))
    b = repo.create_skill(project_id, user_id, _valid_skill("b"))
    # rename b -> a should fail (a exists)
    new_def = _valid_skill("a")
    with pytest.raises(DatabaseConflictError, match="sudah dipakai"):
        repo.update_skill(b.id, user_id, new_def)


def test_update_skill_unknown_id_raises(repo_user_project) -> None:
    repo, user_id, _ = repo_user_project
    with pytest.raises(DatabaseConflictError):
        repo.update_skill("ghost", user_id, _valid_skill("x"))


def test_update_skill_validates_new_definition(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    row = repo.create_skill(project_id, user_id, _valid_skill("a"))
    bad = {"name": "a", "steps": [{"name": "x", "role": "wizard"}]}
    with pytest.raises(SkillValidationError):
        repo.update_skill(row.id, user_id, bad)


# ── delete_skill ─────────────────────────────────────────────────────────────


def test_delete_skill_returns_true_when_deleted(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    row = repo.create_skill(project_id, user_id, _valid_skill("doomed"))
    assert repo.delete_skill(row.id, user_id) is True
    assert repo.get_skill(row.id, user_id) is None


def test_delete_skill_returns_false_when_not_found(repo_user_project) -> None:
    repo, user_id, _ = repo_user_project
    assert repo.delete_skill("ghost", user_id) is False


def test_delete_skill_blocked_for_other_user(repo_user_project, session) -> None:
    repo, user_id, project_id = repo_user_project
    row = repo.create_skill(project_id, user_id, _valid_skill("x"))
    other = UserModel(display_name="Bob", email="bob@x.com")
    session.add(other)
    session.flush()
    assert repo.delete_skill(row.id, other.id) is False
    # Original still exists for owner
    assert repo.get_skill(row.id, user_id) is not None


# ── load_skill_domain (round-trip ke dataclass) ──────────────────────────────


def test_load_skill_domain_returns_validated_dataclass(repo_user_project) -> None:
    repo, user_id, project_id = repo_user_project
    row = repo.create_skill(project_id, user_id, _valid_skill("workflow"))
    skill = repo.load_skill_domain(row)
    assert skill.name == "workflow"
    assert [s.name for s in skill.steps] == ["design", "build"]
