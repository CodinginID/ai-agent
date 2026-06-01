"""Per-namespace project context: decisions, tasks, executions, notes.

File-backed (JSONL append-only + tasks JSON) so context survives restarts.
Keyed by an opaque ``namespace`` string — callers pass ``MessageContext.user_id``
so each operator's context is isolated.

``build_context`` produces a bounded summary injected into the chat prompt so
Qwen can answer with project context without the user repeating themselves.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

_SAFE_NAMESPACE = re.compile(r"[^A-Za-z0-9_-]")


class TaskNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class Decision:
    id: str
    text: str
    created_at: str


@dataclass(frozen=True)
class Note:
    id: str
    text: str
    created_at: str


@dataclass(frozen=True)
class Execution:
    id: str
    summary: str
    status: str
    created_at: str


@dataclass(frozen=True)
class Task:
    id: str
    text: str
    status: str
    created_at: str
    done_at: str | None = None


def _now() -> str:
    return datetime.now().isoformat()


class ProjectContextStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "context"
        self._lock = threading.Lock()

    # ── filesystem helpers ────────────────────────────────────────────────────

    def _ns_dir(self, namespace: str) -> Path:
        safe = _SAFE_NAMESPACE.sub("_", namespace) or "default"
        path = self._root / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _append_jsonl(self, namespace: str, filename: str, row: dict[str, object]) -> None:
        with (self._ns_dir(namespace) / filename).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _read_jsonl(self, namespace: str, filename: str) -> list[dict[str, object]]:
        path = self._ns_dir(namespace) / filename
        if not path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    # ── decisions ─────────────────────────────────────────────────────────────

    def add_decision(self, namespace: str, text: str) -> Decision:
        with self._lock:
            decision = Decision(id=str(uuid4()), text=text, created_at=_now())
            self._append_jsonl(namespace, "decisions.jsonl", decision.__dict__)
            return decision

    def list_decisions(self, namespace: str, limit: int | None = None) -> list[Decision]:
        with self._lock:
            rows = [Decision(**r) for r in self._read_jsonl(namespace, "decisions.jsonl")]  # type: ignore[arg-type]
        rows.reverse()
        return rows[:limit] if limit is not None else rows

    # ── notes (/remember) ──────────────────────────────────────────────────────

    def add_note(self, namespace: str, text: str) -> Note:
        with self._lock:
            note = Note(id=str(uuid4()), text=text, created_at=_now())
            self._append_jsonl(namespace, "notes.jsonl", note.__dict__)
            return note

    def list_notes(self, namespace: str, limit: int | None = None) -> list[Note]:
        with self._lock:
            rows = [Note(**r) for r in self._read_jsonl(namespace, "notes.jsonl")]  # type: ignore[arg-type]
        rows.reverse()
        return rows[:limit] if limit is not None else rows

    # ── executions ─────────────────────────────────────────────────────────────

    def add_execution(self, namespace: str, summary: str, status: str) -> Execution:
        with self._lock:
            execution = Execution(
                id=str(uuid4()), summary=summary, status=status, created_at=_now()
            )
            self._append_jsonl(namespace, "executions.jsonl", execution.__dict__)
            return execution

    def list_executions(self, namespace: str, limit: int | None = None) -> list[Execution]:
        with self._lock:
            rows = [Execution(**r) for r in self._read_jsonl(namespace, "executions.jsonl")]  # type: ignore[arg-type]
        rows.reverse()
        return rows[:limit] if limit is not None else rows

    # ── tasks ──────────────────────────────────────────────────────────────────

    def _tasks_file(self, namespace: str) -> Path:
        return self._ns_dir(namespace) / "tasks.json"

    def _read_tasks(self, namespace: str) -> list[Task]:
        path = self._tasks_file(namespace)
        if not path.exists():
            return []
        data: list[dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))
        return [Task(**row) for row in data]  # type: ignore[arg-type]

    def _write_tasks(self, namespace: str, tasks: list[Task]) -> None:
        self._tasks_file(namespace).write_text(
            json.dumps([t.__dict__ for t in tasks], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_task(self, namespace: str, text: str) -> Task:
        with self._lock:
            tasks = self._read_tasks(namespace)
            next_id = str(max((int(t.id) for t in tasks), default=0) + 1)
            task = Task(id=next_id, text=text, status="open", created_at=_now())
            tasks.append(task)
            self._write_tasks(namespace, tasks)
            return task

    def list_tasks(self, namespace: str) -> list[Task]:
        with self._lock:
            return self._read_tasks(namespace)

    def complete_task(self, namespace: str, task_id: str) -> Task:
        with self._lock:
            tasks = self._read_tasks(namespace)
            for i, task in enumerate(tasks):
                if task.id == task_id:
                    done = Task(
                        id=task.id,
                        text=task.text,
                        status="done",
                        created_at=task.created_at,
                        done_at=_now(),
                    )
                    tasks[i] = done
                    self._write_tasks(namespace, tasks)
                    return done
            raise TaskNotFoundError(f"Task '{task_id}' tidak ditemukan")

    # ── bounded context for prompt injection ────────────────────────────────────

    def build_context(self, namespace: str, max_chars: int = 1500) -> str:
        open_tasks = [t for t in self.list_tasks(namespace) if t.status == "open"]
        decisions = self.list_decisions(namespace, limit=5)
        notes = self.list_notes(namespace, limit=5)

        if not open_tasks and not decisions and not notes:
            return ""

        lines: list[str] = ["## Konteks project"]
        if open_tasks:
            lines.append("Tugas terbuka:")
            lines.extend(f"- [{t.id}] {t.text}" for t in open_tasks)
        if decisions:
            lines.append("Keputusan terbaru:")
            lines.extend(f"- {d.text}" for d in decisions)
        if notes:
            lines.append("Catatan:")
            lines.extend(f"- {n.text}" for n in notes)

        context = "\n".join(lines)
        if len(context) > max_chars:
            context = context[:max_chars].rstrip()
        return context
