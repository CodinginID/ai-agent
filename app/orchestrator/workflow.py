"""WorkflowOrchestrator — jalankan kontrak architect → engineer → reviewer (#6).

Tanggung jawab:
- Validasi setiap artefak SEBELUM hand-off ke role berikutnya.
- Tolak file path yang dihalusinasi (``validate_patch_against_plan``).
- Cap loop engineer↔reviewer (``RevisionPolicy``).
- Catat setiap transisi role ke audit log (auditable).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.workflow import (
    MAX_REVISION_ITERATIONS,
    Patch,
    Plan,
    RevisionPolicy,
    Stage,
    Verdict,
    assert_transition,
    validate_patch_against_plan,
)
from app.ports.audit import AuditLogger
from app.ports.workflow import (
    ArchitectPort,
    ArtifactStore,
    EngineerPort,
    FileChecker,
    ReviewerPort,
)


@dataclass(frozen=True)
class WorkflowResult:
    plan: Plan
    patch: Patch
    verdict: Verdict
    stage: Stage
    revisions: int


@dataclass
class WorkflowOrchestrator:
    architect: ArchitectPort
    engineer: EngineerPort
    reviewer: ReviewerPort
    artifacts: ArtifactStore
    file_checker: FileChecker
    audit: AuditLogger | None = None
    max_iterations: int = MAX_REVISION_ITERATIONS

    def plan(self, goal: str, trace_id: str, context: str = "") -> Plan:
        plan = self.architect.make_plan(goal, trace_id, context)
        self.artifacts.save_plan(plan)
        self._audit_transition(trace_id, "user", "architect", plan_id=plan.plan_id,
                               model=plan.author_model)
        return plan

    def implement_and_review(self, plan_id: str) -> WorkflowResult:
        plan = self.artifacts.get_plan(plan_id)
        if plan is None:
            raise KeyError(f"Plan '{plan_id}' tidak ditemukan")
        trace_id = plan.trace_id

        policy = RevisionPolicy(self.max_iterations)

        stage = Stage.PLANNING
        assert_transition(stage, Stage.IMPLEMENTING)
        stage = Stage.IMPLEMENTING
        self._audit_transition(trace_id, "architect", "engineer", plan_id=plan_id)

        while True:
            patch = self.engineer.implement(plan)
            # Validate BEFORE hand-off to reviewer — rejects hallucinated paths.
            validate_patch_against_plan(patch, plan, self.file_checker.exists)
            self.artifacts.save_patch(patch)

            assert_transition(stage, Stage.REVIEWING)
            stage = Stage.REVIEWING
            self._audit_transition(trace_id, "engineer", "reviewer",
                                   patch_id=patch.patch_id, model=patch.author_model)

            verdict = self.reviewer.review(patch, plan)
            self.artifacts.save_verdict(verdict)

            if verdict.approved:
                assert_transition(stage, Stage.APPROVED)
                stage = Stage.APPROVED
                self._audit_transition(trace_id, "reviewer", "approved",
                                       verdict_id=verdict.verdict_id,
                                       model=verdict.reviewer_model)
                return WorkflowResult(plan, patch, verdict, stage, policy.revisions)

            self._audit_transition(trace_id, "reviewer", "engineer",
                                   verdict_id=verdict.verdict_id, rejected=True)
            policy.record_revision()  # raises LoopLimitExceededError past the cap
            assert_transition(stage, Stage.IMPLEMENTING)
            stage = Stage.IMPLEMENTING

    def review_latest(self, plan_id: str) -> Verdict:
        """Re-review the most recent patch of a plan's trace (powers /review_last)."""
        plan = self.artifacts.get_plan(plan_id)
        if plan is None:
            raise KeyError(f"Plan '{plan_id}' tidak ditemukan")
        patch = self.artifacts.latest_patch(plan.trace_id)
        if patch is None:
            raise KeyError(f"Belum ada patch untuk plan '{plan_id}'")

        verdict = self.reviewer.review(patch, plan)
        self.artifacts.save_verdict(verdict)
        self._audit_transition(plan.trace_id, "engineer", "reviewer",
                               patch_id=patch.patch_id, rereview=True)
        return verdict

    def _audit_transition(
        self, trace_id: str, from_role: str, to_role: str, **fields: object
    ) -> None:
        if self.audit is None:
            return
        self.audit.log(
            "workflow_transition", trace_id,
            from_role=from_role, to_role=to_role, **fields,
        )
