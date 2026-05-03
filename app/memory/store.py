from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from app.memory.models import Project


class ProjectNotFoundError(Exception):
    pass


class ProjectAlreadyExistsError(Exception):
    pass


class ProjectStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._projects_file = data_dir / "projects.json"
        self._chat_project_file = data_dir / "chat_project.json"
        self._lock = threading.Lock()
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        if not self._projects_file.exists():
            self._write_projects([self._make_default_project()])
        if not self._chat_project_file.exists():
            self._chat_project_file.write_text("{}", encoding="utf-8")

    def _make_default_project(self) -> Project:
        now = datetime.now().isoformat()
        return Project(
            id="default",
            name="default",
            root_path=".",
            description="Default project",
            created_at=now,
            updated_at=now,
        )

    def _read_projects(self) -> list[Project]:
        data: list[dict[str, str]] = json.loads(self._projects_file.read_text(encoding="utf-8"))
        return [Project.from_dict(p) for p in data]

    def _write_projects(self, projects: list[Project]) -> None:
        self._projects_file.write_text(
            json.dumps([p.as_dict() for p in projects], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _read_chat_map(self) -> dict[str, str]:
        data: dict[str, str] = json.loads(self._chat_project_file.read_text(encoding="utf-8"))
        return data

    def _write_chat_map(self, mapping: dict[str, str]) -> None:
        self._chat_project_file.write_text(
            json.dumps(mapping, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list_projects(self) -> list[Project]:
        with self._lock:
            return self._read_projects()

    def get_project(self, project_id: str) -> Project | None:
        with self._lock:
            for p in self._read_projects():
                if p.id == project_id or p.name == project_id:
                    return p
        return None

    def add_project(self, name: str, root_path: str, description: str = "") -> Project:
        with self._lock:
            projects = self._read_projects()
            project_id = name.lower().replace(" ", "_").replace("-", "_")
            if any(p.id == project_id or p.name == name for p in projects):
                raise ProjectAlreadyExistsError(f"Project '{name}' sudah ada")
            now = datetime.now().isoformat()
            project = Project(
                id=project_id,
                name=name,
                root_path=root_path,
                description=description,
                created_at=now,
                updated_at=now,
            )
            projects.append(project)
            self._write_projects(projects)
            return project

    def get_active_project_id(self, chat_id: int) -> str:
        return self._read_chat_map().get(str(chat_id), "default")

    def set_active_project(self, chat_id: int, project_id: str) -> None:
        with self._lock:
            mapping = self._read_chat_map()
            mapping[str(chat_id)] = project_id
            self._write_chat_map(mapping)

    def get_active_project(self, chat_id: int, fallback_path: Path) -> Project:
        project_id = self.get_active_project_id(chat_id)
        project = self.get_project(project_id) or self.get_project("default")
        if project is None:
            now = datetime.now().isoformat()
            return Project(
                id="default",
                name="default",
                root_path=str(fallback_path),
                description="",
                created_at=now,
                updated_at=now,
            )
        return project
