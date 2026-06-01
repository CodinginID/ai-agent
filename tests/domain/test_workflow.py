"""Pure-domain tests for the architect/engineer/reviewer workflow contracts (#6)."""

from __future__ import annotations

import pytest

from app.domain.workflow import (
    MAX_REVISION_ITERATIONS,
    HallucinatedPathError,
    InvalidTransitionError,
    LoopLimitExceededError,
    Patch,
    PatchValidationError,
    Plan,
    PlanValidationError,
    RevisionPolicy,
    SameModelError,
    Stage,
    Verdict,
    VerdictValidationError,
    assert_transition,
    require_distinct_models,
    validate_patch_against_plan,
)


def _plan(**kw: object) -> Plan:
    defaults: dict[str, object] = {
        "plan_id": "p1",
        "trace_id": "t1",
        "goal": "add health endpoint",
        "steps": ("edit app/main.py", "add test"),
        "target_files": ("app/main.py", "tests/test_main.py"),
        "author_model": "glm-4",
    }
    defaults.update(kw)
    return Plan(**defaults)  # type: ignore[arg-type]


def _patch(**kw: object) -> Patch:
    defaults: dict[str, object] = {
        "patch_id": "pt1",
        "plan_id": "p1",
        "trace_id": "t1",
        "summary": "implemented health endpoint",
        "changed_files": ("app/main.py",),
        "diff": "--- a/app/main.py\n+++ b/app/main.py",
        "author_model": "codex-1",
    }
    defaults.update(kw)
    return Patch(**defaults)  # type: ignore[arg-type]


# ── Plan validation ───────────────────────────────────────────────────────────


def test_valid_plan_constructs() -> None:
    plan = _plan()
    assert plan.goal == "add health endpoint"
    assert plan.steps


def test_plan_empty_goal_rejected() -> None:
    with pytest.raises(PlanValidationError):
        _plan(goal="   ")


def test_plan_without_steps_rejected() -> None:
    with pytest.raises(PlanValidationError):
        _plan(steps=())


def test_plan_is_frozen() -> None:
    plan = _plan()
    with pytest.raises((AttributeError, TypeError)):
        plan.goal = "x"  # type: ignore[misc]


# ── Patch validation ────────────────────────────────────────────────────────


def test_valid_patch_constructs() -> None:
    assert _patch().changed_files == ("app/main.py",)


def test_patch_without_changed_files_rejected() -> None:
    with pytest.raises(PatchValidationError):
        _patch(changed_files=())


def test_patch_changed_file_declared_in_plan_is_accepted() -> None:
    plan = _plan(target_files=("app/main.py",))
    patch = _patch(changed_files=("app/main.py",))
    validate_patch_against_plan(patch, plan, file_exists=lambda _p: False)


def test_patch_existing_file_not_in_plan_is_accepted() -> None:
    plan = _plan(target_files=("app/other.py",))
    patch = _patch(changed_files=("app/main.py",))
    validate_patch_against_plan(patch, plan, file_exists=lambda p: p == "app/main.py")


def test_patch_hallucinated_path_rejected() -> None:
    plan = _plan(target_files=("app/main.py",))
    patch = _patch(changed_files=("app/ghost_module.py",))
    with pytest.raises(HallucinatedPathError):
        validate_patch_against_plan(patch, plan, file_exists=lambda _p: False)


# ── Verdict validation ────────────────────────────────────────────────────────


def test_approved_verdict_needs_no_comments() -> None:
    v = Verdict(verdict_id="v1", patch_id="pt1", trace_id="t1", approved=True, comments="", reviewer_model="claude-1")
    assert v.approved


def test_rejected_verdict_without_comments_rejected() -> None:
    with pytest.raises(VerdictValidationError):
        Verdict(verdict_id="v1", patch_id="pt1", trace_id="t1", approved=False, comments="  ", reviewer_model="claude-1")


# ── distinct model rule ─────────────────────────────────────────────────────


def test_distinct_models_pass() -> None:
    require_distinct_models(engineer_model="codex-1", reviewer_model="claude-1")


def test_same_model_for_engineer_and_reviewer_rejected() -> None:
    with pytest.raises(SameModelError):
        require_distinct_models(engineer_model="qwen2.5", reviewer_model="qwen2.5")


# ── transition rules ────────────────────────────────────────────────────────


def test_valid_transitions() -> None:
    assert_transition(Stage.PLANNING, Stage.IMPLEMENTING)
    assert_transition(Stage.IMPLEMENTING, Stage.REVIEWING)
    assert_transition(Stage.REVIEWING, Stage.APPROVED)
    assert_transition(Stage.REVIEWING, Stage.IMPLEMENTING)


def test_invalid_transition_rejected() -> None:
    with pytest.raises(InvalidTransitionError):
        assert_transition(Stage.PLANNING, Stage.APPROVED)


def test_no_transition_out_of_approved() -> None:
    with pytest.raises(InvalidTransitionError):
        assert_transition(Stage.APPROVED, Stage.IMPLEMENTING)


# ── loop limit policy ─────────────────────────────────────────────────────────


def test_revision_policy_allows_up_to_max() -> None:
    policy = RevisionPolicy()
    for _ in range(MAX_REVISION_ITERATIONS):
        policy.record_revision()
    assert policy.revisions == MAX_REVISION_ITERATIONS


def test_revision_policy_raises_past_max() -> None:
    policy = RevisionPolicy()
    with pytest.raises(LoopLimitExceededError):
        for _ in range(MAX_REVISION_ITERATIONS + 1):
            policy.record_revision()
