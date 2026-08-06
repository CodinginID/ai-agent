"""WorkflowOrchestrator tests — uses real fakes (not mocks) for the ports."""

from __future__ import annotations

import pytest

from app.domain.workflow import (
    HallucinatedPathError,
    LoopLimitExceededError,
    Patch,
    Plan,
    Stage,
    Verdict,
)
from app.orchestrator.workflow import WorkflowOrchestrator, WorkflowResult

TRACE = "trace-1"


def _plan(target_files: tuple[str, ...] = ("app/main.py",)) -> Plan:
    return Plan(
        plan_id="p1",
        trace_id=TRACE,
        goal="add health endpoint",
        steps=("edit main",),
        target_files=target_files,
        author_model="glm",
    )


def _patch(changed: tuple[str, ...] = ("app/main.py",)) -> Patch:
    return Patch(
        patch_id="pt1",
        plan_id="p1",
        trace_id=TRACE,
        summary="done",
        changed_files=changed,
        diff="diff",
        author_model="codex",
    )


def _verdict(approved: bool, comments: str = "") -> Verdict:
    return Verdict(
        verdict_id="v1",
        patch_id="pt1",
        trace_id=TRACE,
        approved=approved,
        comments=comments or ("looks good" if approved else "fix this"),
        reviewer_model="claude",
    )


class FakeArchitect:
    model = "glm"

    def __init__(self, plan: Plan) -> None:
        self._plan = plan

    def make_plan(self, goal: str, trace_id: str, context: str = "") -> Plan:
        return self._plan


class FakeEngineer:
    model = "codex"

    def __init__(self, patches: list[Patch]) -> None:
        self._patches = iter(patches)

    def implement(self, plan: Plan) -> Patch:
        return next(self._patches)


class FakeReviewer:
    model = "claude"

    def __init__(self, verdicts: list[Verdict]) -> None:
        self._verdicts = iter(verdicts)

    def review(self, patch: Patch, plan: Plan) -> Verdict:
        return next(self._verdicts)


class InMemoryArtifacts:
    def __init__(self) -> None:
        self.plans: dict[str, Plan] = {}
        self.patches: list[Patch] = []
        self.verdicts: list[Verdict] = []

    def save_plan(self, plan: Plan) -> None:
        self.plans[plan.plan_id] = plan

    def get_plan(self, plan_id: str) -> Plan | None:
        return self.plans.get(plan_id)

    def save_patch(self, patch: Patch) -> None:
        self.patches.append(patch)

    def latest_patch(self, trace_id: str) -> Patch | None:
        rows = [p for p in self.patches if p.trace_id == trace_id]
        return rows[-1] if rows else None

    def save_verdict(self, verdict: Verdict) -> None:
        self.verdicts.append(verdict)

    def latest_verdict(self, trace_id: str) -> Verdict | None:
        rows = [v for v in self.verdicts if v.trace_id == trace_id]
        return rows[-1] if rows else None


class FakeFileChecker:
    def __init__(self, existing: set[str] | None = None) -> None:
        self._existing = existing or set()

    def exists(self, path: str) -> bool:
        return path in self._existing


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    def log(self, event: str, trace_id: str, **fields: object) -> None:
        self.events.append((event, trace_id, fields))


def _orch(
    *,
    plan: Plan,
    patches: list[Patch],
    verdicts: list[Verdict],
    file_checker: FakeFileChecker | None = None,
    audit: RecordingAudit | None = None,
    reviewer_model: str = "claude",
) -> tuple[WorkflowOrchestrator, InMemoryArtifacts]:
    artifacts = InMemoryArtifacts()
    artifacts.save_plan(plan)  # simulates a prior /plan call
    reviewer = FakeReviewer(verdicts)
    reviewer.model = reviewer_model  # type: ignore[misc]
    orch = WorkflowOrchestrator(
        architect=FakeArchitect(plan),
        engineer=FakeEngineer(patches),
        reviewer=reviewer,
        artifacts=artifacts,
        file_checker=file_checker or FakeFileChecker({"app/main.py"}),
        audit=audit,
    )
    return orch, artifacts


# ── plan ──────────────────────────────────────────────────────────────────────


def test_plan_saves_artifact_and_returns_plan() -> None:
    orch, artifacts = _orch(plan=_plan(), patches=[], verdicts=[])
    plan = orch.plan("add health endpoint", TRACE)
    assert plan.plan_id == "p1"
    assert artifacts.get_plan("p1") is plan


# ── implement_and_review happy path ───────────────────────────────────────────


def test_approved_on_first_review() -> None:
    orch, _ = _orch(plan=_plan(), patches=[_patch()], verdicts=[_verdict(True)])
    result = orch.implement_and_review("p1")
    assert isinstance(result, WorkflowResult)
    assert result.stage == Stage.APPROVED
    assert result.revisions == 0
    assert result.verdict.approved


def test_rejection_then_approval_counts_one_revision() -> None:
    orch, artifacts = _orch(
        plan=_plan(),
        patches=[_patch(), _patch()],
        verdicts=[_verdict(False), _verdict(True)],
    )
    result = orch.implement_and_review("p1")
    assert result.stage == Stage.APPROVED
    assert result.revisions == 1
    assert len(artifacts.patches) == 2


# ── validations ───────────────────────────────────────────────────────────────


def test_hallucinated_patch_path_aborts_before_review() -> None:
    orch, _ = _orch(
        plan=_plan(target_files=("app/main.py",)),
        patches=[_patch(changed=("app/ghost.py",))],
        verdicts=[_verdict(True)],
        file_checker=FakeFileChecker(set()),
    )
    with pytest.raises(HallucinatedPathError):
        orch.implement_and_review("p1")


def test_same_engineer_reviewer_model_allowed() -> None:
    # Model identik antar posisi diizinkan — yang membedakan skill/spec posisi,
    # bukan identitas model.
    orch, _ = _orch(
        plan=_plan(),
        patches=[_patch()],
        verdicts=[_verdict(True)],
        reviewer_model="codex",  # same as engineer
    )
    result = orch.implement_and_review("p1")
    assert result.verdict.approved is True


def test_loop_cap_raises_when_never_approved() -> None:
    orch, _ = _orch(
        plan=_plan(),
        patches=[_patch() for _ in range(10)],
        verdicts=[_verdict(False) for _ in range(10)],
    )
    with pytest.raises(LoopLimitExceededError):
        orch.implement_and_review("p1")


def test_unknown_plan_id_raises() -> None:
    orch, _ = _orch(plan=_plan(), patches=[], verdicts=[])
    with pytest.raises(KeyError):
        orch.implement_and_review("missing")


# ── review_latest (/review_last) ──────────────────────────────────────────────


def test_review_latest_reruns_reviewer_on_last_patch() -> None:
    orch, _ = _orch(
        plan=_plan(),
        patches=[_patch()],
        verdicts=[_verdict(True), _verdict(False, "needs work")],
    )
    orch.implement_and_review("p1")  # consumes patch + first verdict
    verdict = orch.review_latest("p1")
    assert not verdict.approved
    assert verdict.comments == "needs work"


def test_review_latest_without_patch_raises() -> None:
    orch, _ = _orch(plan=_plan(), patches=[], verdicts=[])
    with pytest.raises(KeyError):
        orch.review_latest("p1")


# ── auditability ──────────────────────────────────────────────────────────────


def test_role_transitions_are_audited() -> None:
    audit = RecordingAudit()
    orch, _ = _orch(
        plan=_plan(),
        patches=[_patch()],
        verdicts=[_verdict(True)],
        audit=audit,
    )
    orch.implement_and_review("p1")
    transition_events = [e for e in audit.events if e[0] == "workflow_transition"]
    pairs = {(e[2].get("from_role"), e[2].get("to_role")) for e in transition_events}
    assert ("architect", "engineer") in pairs
    assert ("engineer", "reviewer") in pairs
    assert ("reviewer", "approved") in pairs
    # every audit event must carry the trace_id
    assert all(e[1] == TRACE for e in audit.events)
