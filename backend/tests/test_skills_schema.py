"""Unit tests untuk Skill DSL schema (``app.domain.skills``).

Pure domain — zero mocks, zero DB.
"""

from __future__ import annotations

import pytest

from app.domain.skills import (
    MAX_DESCRIPTION_LEN,
    MAX_STEPS,
    Manager,
    Skill,
    SkillValidationError,
    Step,
    parse_skill,
    skill_to_dict,
    topological_order,
)

# ── Minimum valid skill ───────────────────────────────────────────────────────


def _minimal_skill_dict() -> dict[str, object]:
    return {
        "name": "trivial",
        "steps": [{"name": "only", "role": "engineer"}],
    }


def test_parse_minimal_skill_succeeds() -> None:
    skill = parse_skill(_minimal_skill_dict())
    assert skill.name == "trivial"
    assert len(skill.steps) == 1
    assert skill.steps[0].name == "only"
    assert skill.steps[0].role == "engineer"
    assert skill.manager is None


def test_parse_full_skill_with_manager_and_dependencies() -> None:
    data = {
        "name": "build-site",
        "description": "End-to-end website build",
        "steps": [
            {"name": "design", "role": "architect", "depends_on": []},
            {"name": "code", "role": "engineer", "depends_on": ["design"]},
            {"name": "review", "role": "reviewer", "depends_on": ["code"]},
        ],
        "manager": {
            "role": "architect",
            "max_revisions": 3,
            "acceptance_criteria": "Production-ready",
        },
    }
    skill = parse_skill(data)
    assert skill.name == "build-site"
    assert skill.description == "End-to-end website build"
    assert [s.name for s in skill.steps] == ["design", "code", "review"]
    assert skill.steps[1].depends_on == ("design",)
    assert skill.manager is not None
    assert skill.manager.max_revisions == 3


def test_parse_uses_role_as_default_step_name() -> None:
    """Step boleh tidak punya 'name' eksplisit kalau pakai role sebagai identifier."""
    data = {
        "name": "x",
        "steps": [{"role": "engineer"}],
    }
    skill = parse_skill(data)
    assert skill.steps[0].name == "engineer"


# ── Validation errors ─────────────────────────────────────────────────────────


def test_reject_non_dict_input() -> None:
    with pytest.raises(SkillValidationError):
        parse_skill("not a dict")  # type: ignore[arg-type]


def test_reject_missing_name() -> None:
    with pytest.raises(SkillValidationError, match="name"):
        parse_skill({"steps": [{"name": "x", "role": "engineer"}]})


def test_reject_empty_steps() -> None:
    with pytest.raises(SkillValidationError, match="steps"):
        parse_skill({"name": "x", "steps": []})


def test_reject_steps_above_cap() -> None:
    steps = [{"name": f"s{i}", "role": "engineer"} for i in range(MAX_STEPS + 1)]
    with pytest.raises(SkillValidationError, match=r"melebihi cap"):
        parse_skill({"name": "x", "steps": steps})


def test_reject_unknown_role() -> None:
    with pytest.raises(SkillValidationError, match="wizard"):
        parse_skill({
            "name": "x",
            "steps": [{"name": "a", "role": "wizard"}],
        })


def test_reject_duplicate_step_names() -> None:
    with pytest.raises(SkillValidationError, match="duplikat"):
        parse_skill({
            "name": "x",
            "steps": [
                {"name": "a", "role": "engineer"},
                {"name": "a", "role": "reviewer"},
            ],
        })


def test_reject_depends_on_referencing_nonexistent_step() -> None:
    with pytest.raises(SkillValidationError, match="ghost"):
        parse_skill({
            "name": "x",
            "steps": [
                {"name": "a", "role": "engineer", "depends_on": ["ghost"]},
            ],
        })


def test_reject_self_dependency() -> None:
    with pytest.raises(SkillValidationError, match="dirinya sendiri"):
        parse_skill({
            "name": "x",
            "steps": [
                {"name": "a", "role": "engineer", "depends_on": ["a"]},
            ],
        })


def test_reject_cycle_in_dependencies() -> None:
    with pytest.raises(SkillValidationError, match=r"[Cc]ycle"):
        parse_skill({
            "name": "x",
            "steps": [
                {"name": "a", "role": "engineer", "depends_on": ["b"]},
                {"name": "b", "role": "engineer", "depends_on": ["c"]},
                {"name": "c", "role": "engineer", "depends_on": ["a"]},
            ],
        })


def test_reject_description_too_long() -> None:
    with pytest.raises(SkillValidationError, match="description"):
        parse_skill({
            "name": "x",
            "description": "X" * (MAX_DESCRIPTION_LEN + 1),
            "steps": [{"name": "a", "role": "engineer"}],
        })


def test_reject_unknown_role_in_manager() -> None:
    with pytest.raises(SkillValidationError, match="ceo"):
        parse_skill({
            "name": "x",
            "steps": [{"name": "a", "role": "engineer"}],
            "manager": {"role": "ceo"},
        })


def test_reject_negative_max_revisions_in_manager() -> None:
    with pytest.raises(SkillValidationError, match="max_revisions"):
        parse_skill({
            "name": "x",
            "steps": [{"name": "a", "role": "engineer"}],
            "manager": {"role": "architect", "max_revisions": -1},
        })


# ── skill_to_dict round-trip ─────────────────────────────────────────────────


def test_round_trip_minimal() -> None:
    data = _minimal_skill_dict()
    skill = parse_skill(data)
    back = skill_to_dict(skill)
    again = parse_skill(back)
    assert again == skill


def test_round_trip_full_with_manager() -> None:
    data = {
        "name": "x",
        "description": "desc",
        "steps": [
            {"name": "a", "role": "engineer", "depends_on": []},
            {"name": "b", "role": "reviewer", "depends_on": ["a"], "produces": "review"},
        ],
        "manager": {
            "role": "architect",
            "max_revisions": 5,
            "acceptance_criteria": "good enough",
        },
    }
    skill = parse_skill(data)
    again = parse_skill(skill_to_dict(skill))
    assert again == skill


# ── topological_order ────────────────────────────────────────────────────────


def test_topo_order_simple_chain() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [
            {"name": "c", "role": "reviewer", "depends_on": ["b"]},
            {"name": "b", "role": "engineer", "depends_on": ["a"]},
            {"name": "a", "role": "engineer", "depends_on": []},
        ],
    })
    order = topological_order(skill)
    assert [s.name for s in order] == ["a", "b", "c"]


def test_topo_order_is_stable_for_independent_steps() -> None:
    """Step yang bisa paralel mengikuti urutan deklarasi user."""
    skill = parse_skill({
        "name": "x",
        "steps": [
            {"name": "first",  "role": "engineer", "depends_on": []},
            {"name": "second", "role": "engineer", "depends_on": []},
            {"name": "third",  "role": "reviewer", "depends_on": ["first", "second"]},
        ],
    })
    order = topological_order(skill)
    assert [s.name for s in order] == ["first", "second", "third"]


def test_topo_order_complex_dag() -> None:
    skill = parse_skill({
        "name": "x",
        "steps": [
            {"name": "design",  "role": "architect", "depends_on": []},
            {"name": "copy",    "role": "engineer",  "depends_on": ["design"]},
            {"name": "code",    "role": "engineer",  "depends_on": ["design", "copy"]},
            {"name": "review",  "role": "reviewer",  "depends_on": ["code"]},
        ],
    })
    order = topological_order(skill)
    names = [s.name for s in order]
    # Constraints: design < copy < code < review; design < code
    assert names.index("design") < names.index("copy")
    assert names.index("copy") < names.index("code")
    assert names.index("code") < names.index("review")


# ── Dataclass behavior ───────────────────────────────────────────────────────


def test_skill_dataclass_is_frozen() -> None:
    from dataclasses import FrozenInstanceError
    skill = Skill(name="x", steps=(Step(name="a", role="engineer"),))
    with pytest.raises(FrozenInstanceError):
        skill.name = "y"  # type: ignore[misc]


def test_manager_dataclass_is_frozen() -> None:
    from dataclasses import FrozenInstanceError
    m = Manager(role="architect")
    with pytest.raises(FrozenInstanceError):
        m.max_revisions = 99  # type: ignore[misc]
