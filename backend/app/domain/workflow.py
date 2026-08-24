"""Architect → Engineer → Reviewer workflow contracts (issue #6).

Pure domain: zero import dari adapter/framework. Mendefinisikan artefak yang
dihand-off antar role (``Plan`` → ``Patch`` → ``Verdict``), aturan transisi
state machine, dan batas iterasi loop revisi.

Yang membedakan tiap posisi adalah SKILL/spec agent worker di posisi itu
(prompt, tools, access_mode) — bukan identitas model. Model bebas: boleh sama
atau beda antar posisi.

Penamaan sengaja ``Plan``/``Patch``/``Verdict`` (bukan ``ExecutionPlan`` /
``TaskPlan`` yang sudah ada) karena ini artefak workflow agentik, bukan plan
eksekusi command server.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

MAX_REVISION_ITERATIONS = 3


# ── Errors ────────────────────────────────────────────────────────────────────


class WorkflowError(ValueError):
    """Base untuk semua pelanggaran kontrak workflow."""


class PlanValidationError(WorkflowError): ...


class PatchValidationError(WorkflowError): ...


class HallucinatedPathError(PatchValidationError):
    """Patch menyentuh file yang tidak ada DAN tidak dideklarasikan di plan."""


class VerdictValidationError(WorkflowError): ...


class InvalidTransitionError(WorkflowError):
    """Transisi state machine yang tidak diizinkan."""


class LoopLimitExceededError(WorkflowError):
    """Loop engineer↔reviewer melewati batas iterasi."""


# ── Stages ────────────────────────────────────────────────────────────────────


class Stage(StrEnum):
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    REVIEWING = "reviewing"
    APPROVED = "approved"


_ALLOWED_TRANSITIONS: dict[Stage, frozenset[Stage]] = {
    Stage.PLANNING: frozenset({Stage.IMPLEMENTING}),
    Stage.IMPLEMENTING: frozenset({Stage.REVIEWING}),
    Stage.REVIEWING: frozenset({Stage.IMPLEMENTING, Stage.APPROVED}),
    Stage.APPROVED: frozenset(),
}


def assert_transition(frm: Stage, to: Stage) -> None:
    if to not in _ALLOWED_TRANSITIONS.get(frm, frozenset()):
        raise InvalidTransitionError(f"Transisi {frm} → {to} tidak diizinkan")


# ── Artifacts ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Plan:
    plan_id: str
    trace_id: str
    goal: str
    steps: tuple[str, ...]
    target_files: tuple[str, ...]
    author_model: str

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise PlanValidationError("Plan.goal tidak boleh kosong")
        if not self.steps:
            raise PlanValidationError("Plan.steps tidak boleh kosong")


@dataclass(frozen=True)
class Patch:
    patch_id: str
    plan_id: str
    trace_id: str
    summary: str
    changed_files: tuple[str, ...]
    diff: str
    author_model: str

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise PatchValidationError("Patch.plan_id tidak boleh kosong")
        if not self.changed_files:
            raise PatchValidationError("Patch.changed_files tidak boleh kosong")


@dataclass(frozen=True)
class Verdict:
    verdict_id: str
    patch_id: str
    trace_id: str
    approved: bool
    comments: str
    reviewer_model: str

    def __post_init__(self) -> None:
        if not self.approved and not self.comments.strip():
            raise VerdictValidationError(
                "Verdict yang menolak wajib menyertakan comments"
            )


# ── Cross-artifact rules ──────────────────────────────────────────────────────


def validate_patch_against_plan(
    patch: Patch, plan: Plan, file_exists: Callable[[str], bool]
) -> None:
    """Tolak file yang dihalusinasi: setiap file yang diubah harus sudah ada
    di repo ATAU dideklarasikan di ``plan.target_files``."""
    declared = set(plan.target_files)
    for path in patch.changed_files:
        if path not in declared and not file_exists(path):
            raise HallucinatedPathError(
                f"Patch menyentuh '{path}' yang tidak ada di repo dan tidak "
                f"dideklarasikan di plan"
            )


# ── Loop limit policy ─────────────────────────────────────────────────────────


@dataclass
class RevisionPolicy:
    max_iterations: int = MAX_REVISION_ITERATIONS
    _count: int = field(default=0, init=False)

    @property
    def revisions(self) -> int:
        return self._count

    def record_revision(self) -> int:
        self._count += 1
        if self._count > self.max_iterations:
            raise LoopLimitExceededError(
                f"Loop revisi melewati batas {self.max_iterations} iterasi"
            )
        return self._count
