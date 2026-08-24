"""Prompt-based fallback adapters + file-backed artifact store (issue #6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.adapters.workflow_artifacts import FileArtifactStore, RepoFileChecker
from app.adapters.workflow_fallback import (
    PromptArchitect,
    PromptEngineer,
    PromptReviewer,
)
from app.domain.workflow import Patch, Plan, Verdict


def _ai(response: str) -> MagicMock:
    ai = MagicMock()
    ai.chat.return_value = response
    return ai


# ── PromptArchitect ────────────────────────────────────────────────────────


def test_architect_parses_json_into_plan() -> None:
    ai = _ai('{"goal":"add health","steps":["edit main","add test"],'
             '"target_files":["app/main.py","tests/test_main.py"]}')
    architect = PromptArchitect(ai=ai, model="glm")
    plan = architect.make_plan("add health endpoint", "trace-1")
    assert isinstance(plan, Plan)
    assert plan.trace_id == "trace-1"
    assert plan.steps == ("edit main", "add test")
    assert plan.target_files == ("app/main.py", "tests/test_main.py")
    assert plan.author_model == "glm"


def test_architect_malformed_response_falls_back_to_usable_plan() -> None:
    architect = PromptArchitect(ai=_ai("sorry I cannot"), model="glm")
    plan = architect.make_plan("do thing", "trace-1")
    assert plan.goal == "do thing"
    assert plan.steps  # never empty (Plan would reject)


# ── PromptEngineer ───────────────────────────────────────────────────────────


def _plan() -> Plan:
    return Plan(
        plan_id="p1", trace_id="trace-1", goal="g", steps=("s",),
        target_files=("app/main.py",), author_model="glm",
    )


def test_engineer_parses_json_into_patch() -> None:
    ai = _ai('{"summary":"did it","changed_files":["app/main.py"],"diff":"@@"}')
    engineer = PromptEngineer(ai=ai, model="codex")
    patch = engineer.implement(_plan())
    assert isinstance(patch, Patch)
    assert patch.plan_id == "p1"
    assert patch.changed_files == ("app/main.py",)
    assert patch.author_model == "codex"


def test_engineer_defaults_changed_files_to_plan_targets() -> None:
    ai = _ai('{"summary":"did it","changed_files":[],"diff":"@@"}')
    engineer = PromptEngineer(ai=ai, model="codex")
    patch = engineer.implement(_plan())
    assert patch.changed_files == ("app/main.py",)


# ── PromptReviewer ───────────────────────────────────────────────────────────


def test_reviewer_parses_approved_verdict() -> None:
    ai = _ai('{"approved":true,"comments":"lgtm"}')
    reviewer = PromptReviewer(ai=ai, model="claude")
    patch = Patch(patch_id="pt1", plan_id="p1", trace_id="trace-1", summary="s",
                  changed_files=("app/main.py",), diff="d", author_model="codex")
    verdict = reviewer.review(patch, _plan())
    assert verdict.approved
    assert verdict.reviewer_model == "claude"


def test_reviewer_rejection_without_comments_gets_default() -> None:
    ai = _ai('{"approved":false,"comments":""}')
    reviewer = PromptReviewer(ai=ai, model="claude")
    patch = Patch(patch_id="pt1", plan_id="p1", trace_id="trace-1", summary="s",
                  changed_files=("app/main.py",), diff="d", author_model="codex")
    verdict = reviewer.review(patch, _plan())
    assert not verdict.approved
    assert verdict.comments.strip()  # default comment so Verdict validation passes


# ── FileArtifactStore ─────────────────────────────────────────────────────────


def test_artifact_store_plan_roundtrip(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path)
    store.save_plan(_plan())
    loaded = store.get_plan("p1")
    assert loaded is not None
    assert loaded.goal == "g"
    assert loaded.target_files == ("app/main.py",)


def test_artifact_store_unknown_plan_returns_none(tmp_path: Path) -> None:
    assert FileArtifactStore(tmp_path).get_plan("nope") is None


def test_artifact_store_latest_patch_and_verdict(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path)
    store.save_patch(Patch(patch_id="pt1", plan_id="p1", trace_id="trace-1", summary="a",
                           changed_files=("app/main.py",), diff="d", author_model="codex"))
    store.save_patch(Patch(patch_id="pt2", plan_id="p1", trace_id="trace-1", summary="b",
                           changed_files=("app/main.py",), diff="d", author_model="codex"))
    store.save_verdict(Verdict(verdict_id="v1", patch_id="pt2", trace_id="trace-1",
                               approved=True, comments="", reviewer_model="claude"))
    assert store.latest_patch("trace-1").patch_id == "pt2"  # type: ignore[union-attr]
    assert store.latest_verdict("trace-1").approved is True  # type: ignore[union-attr]


def test_artifact_store_survives_reopen(tmp_path: Path) -> None:
    FileArtifactStore(tmp_path).save_plan(_plan())
    assert FileArtifactStore(tmp_path).get_plan("p1") is not None


# ── RepoFileChecker ───────────────────────────────────────────────────────────


def test_repo_file_checker_detects_existing_and_missing(tmp_path: Path) -> None:
    (tmp_path / "real.py").write_text("x", encoding="utf-8")
    checker = RepoFileChecker(tmp_path)
    assert checker.exists("real.py")
    assert not checker.exists("ghost.py")
