"""Tests for role profiles ("skills & rules") and step-prompt rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.roles import (
    ROLE_PROFILES,
    build_step_prompt,
    get_role_profile,
)


@pytest.mark.parametrize("role", sorted(ROLE_PROFILES))
def test_every_profile_has_title_and_rules(role: str) -> None:
    profile = ROLE_PROFILES[role]
    assert profile.title
    assert profile.mission
    assert len(profile.rules) > 0
    assert all(r.strip() for r in profile.rules)


def test_known_roles_present() -> None:
    for role in ("engineer", "reviewer", "research", "infra", "planner", "tester"):
        assert role in ROLE_PROFILES


def test_unknown_role_falls_back_to_generic() -> None:
    profile = get_role_profile("does-not-exist")
    assert profile.role == "worker"
    assert profile.title
    assert len(profile.rules) > 0


def test_get_role_profile_is_case_insensitive() -> None:
    assert get_role_profile("ENGINEER").role == "engineer"
    assert get_role_profile(" reviewer ").role == "reviewer"


def test_build_step_prompt_contains_role_title_and_step_text() -> None:
    prompt = build_step_prompt(
        "engineer",
        "add a /health route",
        task_title="Add health endpoint",
        task_summary="expose liveness check",
        step_order=1,
        step_total=2,
    )
    assert "Engineer" in prompt
    assert "add a /health route" in prompt
    assert "Add health endpoint" in prompt
    assert "1/2" in prompt
    assert "Hasil:" in prompt  # generic output contract present


def test_build_step_prompt_unknown_role_uses_generic_profile() -> None:
    prompt = build_step_prompt(
        "some_new_role",
        "do the thing",
        task_title="T",
        task_summary="S",
        step_order=1,
        step_total=1,
    )
    assert "Worker" in prompt
    assert "do the thing" in prompt


def test_build_step_prompt_includes_context_when_given() -> None:
    prompt = build_step_prompt(
        "research",
        "investigate the outage",
        task_title="T",
        task_summary="S",
        step_order=1,
        step_total=1,
        context="previous step found high CPU",
    )
    assert "previous step found high CPU" in prompt


def test_planner_profile_has_no_generic_output_contract() -> None:
    """Planner already dictates its own JSON schema — no conflicting contract."""
    prompt = build_step_prompt(
        "planner",
        "Respond with JSON only: {...}",
        task_title="Decompose",
        task_summary="req",
        step_order=1,
        step_total=1,
    )
    assert "Hasil:" not in prompt


def test_project_override_appended_when_file_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.agents.roles as roles_mod

    monkeypatch.setattr(roles_mod, "BASE_DIR", tmp_path)
    roles_dir = tmp_path / "data" / "roles"
    roles_dir.mkdir(parents=True)
    (roles_dir / "engineer.md").write_text("Selalu tulis docstring Indonesia.", encoding="utf-8")

    prompt = build_step_prompt(
        "engineer",
        "do X",
        task_title="T",
        task_summary="S",
        step_order=1,
        step_total=1,
    )
    assert "Aturan tambahan proyek" in prompt
    assert "Selalu tulis docstring Indonesia." in prompt


def test_no_project_override_when_file_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.agents.roles as roles_mod

    monkeypatch.setattr(roles_mod, "BASE_DIR", tmp_path)
    prompt = build_step_prompt(
        "engineer",
        "do X",
        task_title="T",
        task_summary="S",
        step_order=1,
        step_total=1,
    )
    assert "Aturan tambahan proyek" not in prompt
