"""Unit tests for capability registry — pure domain, zero mocks."""

from __future__ import annotations

import pytest

from app.domain.capabilities import (
    DEFAULT_AGENT_CAPABILITIES,
    KNOWN_CAPABILITY_TAGS,
    ROLE_REQUIRED_CAPABILITIES,
    CapabilityMismatchError,
    UnknownRoleError,
    capabilities_for_agent,
    required_for_role,
    validate_role_assignment,
)

# ── Vocabulary integrity ──────────────────────────────────────────────────────


def test_all_default_agent_capabilities_use_known_tags() -> None:
    for agent_id, tags in DEFAULT_AGENT_CAPABILITIES.items():
        unknown = tags - KNOWN_CAPABILITY_TAGS
        assert not unknown, f"agent {agent_id} pakai tag tidak dikenal: {unknown}"


def test_all_role_requirements_use_known_tags() -> None:
    for role, required in ROLE_REQUIRED_CAPABILITIES.items():
        unknown = required - KNOWN_CAPABILITY_TAGS
        assert not unknown, f"role {role} butuh tag tidak dikenal: {unknown}"


def test_default_agents_include_built_ins() -> None:
    """Pastikan codex/claude/glm punya entri — biar /agents flow tidak break."""
    for agent_id in ("codex", "claude", "glm"):
        assert agent_id in DEFAULT_AGENT_CAPABILITIES


def test_default_roles_match_valid_roles_constant() -> None:
    """Sinkron dengan ``VALID_ROLES`` di ``app.adapters.agent_configs``."""
    from app.adapters.agent_configs import VALID_ROLES
    assert set(ROLE_REQUIRED_CAPABILITIES.keys()) == set(VALID_ROLES)


# ── capabilities_for_agent ────────────────────────────────────────────────────


def test_capabilities_for_known_agent_returns_default_set() -> None:
    assert capabilities_for_agent("codex") == DEFAULT_AGENT_CAPABILITIES["codex"]


def test_capabilities_for_unknown_agent_returns_empty() -> None:
    assert capabilities_for_agent("nonexistent-agent-xyz") == frozenset()


# ── required_for_role ─────────────────────────────────────────────────────────


def test_required_for_known_role_returns_set() -> None:
    assert required_for_role("engineer") == frozenset({"code"})


def test_required_for_unknown_role_raises() -> None:
    with pytest.raises(UnknownRoleError) as exc:
        required_for_role("fortune-teller")
    assert "fortune-teller" in str(exc.value)
    # Error message should list known roles untuk membantu user
    for known in ("engineer", "reviewer", "architect"):
        assert known in str(exc.value)


# ── validate_role_assignment ──────────────────────────────────────────────────


def test_validate_passes_for_default_engineer_codex() -> None:
    validate_role_assignment("codex", "engineer")  # tidak boleh raise


def test_validate_passes_for_default_reviewer_claude() -> None:
    validate_role_assignment("claude", "reviewer")


def test_validate_passes_for_default_architect_glm() -> None:
    validate_role_assignment("glm", "architect")


def test_validate_passes_when_agent_has_superset_of_required() -> None:
    """Agent dengan capability lebih dari yang dibutuhkan tetap OK."""
    # Claude punya {code, review, reason, write}; engineer butuh {code}.
    validate_role_assignment("claude", "engineer")


def test_validate_rejects_codex_as_reviewer() -> None:
    """Codex hanya punya 'code', reviewer butuh 'code' + 'review'."""
    with pytest.raises(CapabilityMismatchError) as exc:
        validate_role_assignment("codex", "reviewer")
    assert "review" in str(exc.value)
    assert "codex" in str(exc.value)
    assert "reviewer" in str(exc.value)


def test_validate_rejects_codex_as_architect() -> None:
    """Codex tidak punya 'reason', architect butuh 'reason'."""
    with pytest.raises(CapabilityMismatchError):
        validate_role_assignment("codex", "architect")


def test_validate_rejects_unknown_agent_for_any_role() -> None:
    """Unknown agent = empty capabilities = gagal validasi semua role yang butuh apapun."""
    with pytest.raises(CapabilityMismatchError):
        validate_role_assignment("unknown-agent", "engineer")


def test_validate_raises_unknown_role_for_unknown_role_name() -> None:
    """Typo di role name harus diteriakkan — bukan silently lulus."""
    with pytest.raises(UnknownRoleError):
        validate_role_assignment("codex", "engineeer")  # typo


# ── Wiring: UserAgentConfigRepository.upsert calls validate ───────────────────


@pytest.fixture()
def user_agent_config_repo(tmp_path):
    """Repository yang pakai sqlite in-memory — cukup untuk wiring test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.adapters.agent_configs import UserAgentConfigRepository
    from app.adapters.database.models import Base, UserModel

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        session.add(UserModel(id="user-1", display_name="Alice", email="a@x.com"))
        session.commit()

    return UserAgentConfigRepository(factory)


def test_upsert_with_valid_role_succeeds(user_agent_config_repo) -> None:
    cfg = user_agent_config_repo.upsert("user-1", "codex", role="engineer")
    assert cfg.role == "engineer"


def test_upsert_with_invalid_role_raises_before_persisting(user_agent_config_repo) -> None:
    """Kalau validasi fail, row tidak boleh ada di DB."""
    with pytest.raises(CapabilityMismatchError):
        user_agent_config_repo.upsert("user-1", "codex", role="reviewer")
    assert user_agent_config_repo.get("user-1", "codex") is None


def test_upsert_without_role_skips_validation(user_agent_config_repo) -> None:
    """Set enabled/model tanpa role tidak boleh trigger validasi."""
    cfg = user_agent_config_repo.upsert("user-1", "codex", enabled=True)
    assert cfg.enabled is True
    assert cfg.role == "engineer"  # default dari DEFAULT_ROLE
