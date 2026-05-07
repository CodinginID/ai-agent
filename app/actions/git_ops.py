"""Git operation actions — all run in project_dir, no shell=True."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.executor.actions import ActionMeta, ActionRegistry
from app.executor.runner import run_safe


class GitOperationError(Exception):
    """Git command failed or is misconfigured."""


@dataclass
class GitStatusAction:
    """Get current git status."""

    project_dir: Path = field(default_factory=Path)

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Show current git repository status"

    def execute(self, params: dict | None = None) -> str:
        output, _ = run_safe(
            ["git", "status", "--short", "--branch"],
            cwd=self.project_dir,
        )
        return output


@dataclass
class GitDiffAction:
    """Show git diff."""

    project_dir: Path = field(default_factory=Path)

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return "Show git diff. Params: staged (bool, default False)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        staged = bool(params.get("staged", False))
        args = ["git", "diff"]
        if staged:
            args.append("--cached")
        output, _ = run_safe(args, cwd=self.project_dir)
        return output or "(tidak ada perubahan)"


@dataclass
class GitLogAction:
    """Show recent git log."""

    project_dir: Path = field(default_factory=Path)

    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return "Show git log. Params: n (int, default 10)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        try:
            n = int(params.get("n", 10))
        except (TypeError, ValueError):
            n = 10
        n = max(1, min(n, 50))  # cap between 1 and 50
        output, _ = run_safe(
            ["git", "log", "--oneline", f"-{n}"],
            cwd=self.project_dir,
        )
        return output or "(tidak ada commit)"


@dataclass
class GitAddAction:
    """Stage files for commit."""

    project_dir: Path = field(default_factory=Path)

    @property
    def name(self) -> str:
        return "git_add"

    @property
    def description(self) -> str:
        return "Stage files. Params: files (list[str]) or '.' for all"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        files = params.get("files", [])

        if isinstance(files, str):
            # Accept "." or a single filename as string
            file_list = [files] if files else ["."]
        elif isinstance(files, list):
            file_list = [str(f) for f in files] if files else ["."]
        else:
            file_list = ["."]

        output, returncode = run_safe(
            ["git", "add", "--", *file_list],
            cwd=self.project_dir,
        )
        if returncode != 0:
            return f"git add gagal:\n{output}"
        return f"Berhasil di-stage: {', '.join(file_list)}"


@dataclass
class GitCommitAction:
    """Commit staged changes."""

    project_dir: Path = field(default_factory=Path)

    @property
    def name(self) -> str:
        return "git_commit"

    @property
    def description(self) -> str:
        return "Commit with message. Params: message (str)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        message = str(params.get("message", "")).strip()
        if not message:
            return "Error: parameter 'message' wajib diisi."

        output, returncode = run_safe(
            ["git", "commit", "-m", message],
            cwd=self.project_dir,
        )
        if returncode != 0:
            return f"git commit gagal:\n{output}"
        return output


@dataclass
class GitPushAction:
    """Push to remote."""

    project_dir: Path = field(default_factory=Path)

    @property
    def name(self) -> str:
        return "git_push"

    @property
    def description(self) -> str:
        return "Push current branch. Params: remote (str, default 'origin')"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        remote = str(params.get("remote", "origin")).strip() or "origin"

        # Validate remote name: alphanumeric, dash, dot, underscore only
        import re
        if not re.fullmatch(r"[a-zA-Z0-9_.\-]+", remote):
            return f"Nama remote tidak valid: {remote!r}"

        output, returncode = run_safe(
            ["git", "push", remote],
            cwd=self.project_dir,
        )
        if returncode != 0:
            return f"git push gagal:\n{output}"
        return output or "Push berhasil."


@dataclass
class GitBranchAction:
    """List or create branches."""

    project_dir: Path = field(default_factory=Path)

    @property
    def name(self) -> str:
        return "git_branch"

    @property
    def description(self) -> str:
        return "List or create branch. Params: name (str, optional for create)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        name = str(params.get("name", "")).strip()

        if name:
            # Validate branch name: no shell metacharacters
            import re
            if not re.fullmatch(r"[a-zA-Z0-9_./\-]+", name):
                return f"Nama branch tidak valid: {name!r}"
            output, returncode = run_safe(
                ["git", "checkout", "-b", name],
                cwd=self.project_dir,
            )
            if returncode != 0:
                return f"git checkout -b gagal:\n{output}"
            return output or f"Branch '{name}' dibuat."

        output, _ = run_safe(["git", "branch", "-a"], cwd=self.project_dir)
        return output or "(tidak ada branch)"


def register_git_ops(registry: ActionRegistry, project_dir: Path) -> None:
    """Register all git operation actions into *registry*."""
    actions = [
        GitStatusAction(project_dir=project_dir),
        GitDiffAction(project_dir=project_dir),
        GitLogAction(project_dir=project_dir),
        GitAddAction(project_dir=project_dir),
        GitCommitAction(project_dir=project_dir),
        GitPushAction(project_dir=project_dir),
        GitBranchAction(project_dir=project_dir),
    ]

    risk_map: dict[str, str] = {
        "git_status": "low",
        "git_diff":   "low",
        "git_log":    "low",
        "git_add":    "medium",
        "git_commit": "medium",
        "git_push":   "high",
        "git_branch": "medium",
    }

    for action in actions:
        risk = risk_map.get(action.name, "medium")
        registry.register(ActionMeta(
            name=action.name,
            description=action.description,
            risk_level=risk,
            requires_approval=(risk == "high"),
            handler=action.execute,
        ))
