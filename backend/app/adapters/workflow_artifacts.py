"""File-backed artifact store + repo file checker untuk workflow (issue #6).

``FileArtifactStore`` mempersistensi Plan/Patch/Verdict di bawah ``data/workflow``:
- plans di-index by ``plan_id`` (``plans/<plan_id>.json``)
- patches & verdicts di-append per ``trace_id`` (``traces/<trace_id>/*.jsonl``)

``RepoFileChecker`` mengecek keberadaan file relatif terhadap project root —
dipakai orchestrator untuk menolak path yang dihalusinasi.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.workflow import Patch, Plan, Verdict

_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _safe(value: str) -> str:
    return _SAFE.sub("_", value) or "default"


def _from_plan(d: dict[str, Any]) -> Plan:
    return Plan(
        plan_id=d["plan_id"], trace_id=d["trace_id"], goal=d["goal"],
        steps=tuple(d["steps"]), target_files=tuple(d["target_files"]),
        author_model=d["author_model"],
    )


def _from_patch(d: dict[str, Any]) -> Patch:
    return Patch(
        patch_id=d["patch_id"], plan_id=d["plan_id"], trace_id=d["trace_id"],
        summary=d["summary"], changed_files=tuple(d["changed_files"]),
        diff=d["diff"], author_model=d["author_model"],
    )


def _from_verdict(d: dict[str, Any]) -> Verdict:
    return Verdict(
        verdict_id=d["verdict_id"], patch_id=d["patch_id"], trace_id=d["trace_id"],
        approved=d["approved"], comments=d["comments"], reviewer_model=d["reviewer_model"],
    )


class FileArtifactStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "workflow"
        self._plans = self._root / "plans"
        self._traces = self._root / "traces"
        self._lock = threading.Lock()

    def _trace_dir(self, trace_id: str) -> Path:
        path = self._traces / _safe(trace_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_plan(self, plan: Plan) -> None:
        with self._lock:
            self._plans.mkdir(parents=True, exist_ok=True)
            (self._plans / f"{_safe(plan.plan_id)}.json").write_text(
                json.dumps(plan.__dict__, ensure_ascii=False), encoding="utf-8"
            )

    def get_plan(self, plan_id: str) -> Plan | None:
        path = self._plans / f"{_safe(plan_id)}.json"
        if not path.exists():
            return None
        return _from_plan(json.loads(path.read_text(encoding="utf-8")))

    def save_patch(self, patch: Patch) -> None:
        with self._lock, (self._trace_dir(patch.trace_id) / "patches.jsonl").open(
            "a", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(patch.__dict__, ensure_ascii=False) + "\n")

    def latest_patch(self, trace_id: str) -> Patch | None:
        rows = self._read_jsonl(self._traces / _safe(trace_id) / "patches.jsonl")
        return _from_patch(rows[-1]) if rows else None

    def save_verdict(self, verdict: Verdict) -> None:
        with self._lock, (self._trace_dir(verdict.trace_id) / "verdicts.jsonl").open(
            "a", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(verdict.__dict__, ensure_ascii=False) + "\n")

    def latest_verdict(self, trace_id: str) -> Verdict | None:
        rows = self._read_jsonl(self._traces / _safe(trace_id) / "verdicts.jsonl")
        return _from_verdict(rows[-1]) if rows else None

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


@dataclass
class RepoFileChecker:
    root: Path

    def exists(self, path: str) -> bool:
        return (self.root / path).exists()
