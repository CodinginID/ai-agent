"""Ports untuk workflow agentik (issue #6).

Tiga role port (Architect/Engineer/Reviewer) menghasilkan artefak domain.
``ArtifactStore`` mempersistensi artefak per ``trace_id``. ``FileChecker``
dipakai untuk menolak file path yang dihalusinasi.
"""

from typing import Protocol

from app.domain.workflow import Patch, Plan, Verdict


class ArchitectPort(Protocol):
    model: str

    def make_plan(self, goal: str, trace_id: str, context: str = "") -> Plan: ...


class EngineerPort(Protocol):
    model: str

    def implement(self, plan: Plan) -> Patch: ...


class ReviewerPort(Protocol):
    model: str

    def review(self, patch: Patch, plan: Plan) -> Verdict: ...


class ArtifactStore(Protocol):
    def save_plan(self, plan: Plan) -> None: ...
    def get_plan(self, plan_id: str) -> Plan | None: ...
    def save_patch(self, patch: Patch) -> None: ...
    def latest_patch(self, trace_id: str) -> Patch | None: ...
    def save_verdict(self, verdict: Verdict) -> None: ...
    def latest_verdict(self, trace_id: str) -> Verdict | None: ...


class FileChecker(Protocol):
    def exists(self, path: str) -> bool: ...
