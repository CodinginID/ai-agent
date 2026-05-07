"""GitHub Issues actions — wrap async GitHubAdapter calls for sync ActionRegistry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.adapters.github import GitHubAdapter, GitHubAPIError, GitHubUnavailableError
from app.executor.actions import ActionMeta, ActionRegistry


def _run_async(coro: object) -> object:
    """Execute an async coroutine from a synchronous context.

    Falls back to creating a new event loop if no running loop exists (the
    typical case in bot.py / composition root). If a loop is already running
    (tests or HTTP handlers) callers should use asyncio.create_task instead.
    """
    import inspect
    if not inspect.iscoroutine(coro):
        raise TypeError(f"Expected coroutine, got {type(coro)}")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an async context — must not call loop.run_until_complete.
            # Create a new thread-bound event loop as a safe fallback.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)  # type: ignore[arg-type]


@dataclass
class GitHubCreateIssueAction:
    """Create a new GitHub issue."""

    github: GitHubAdapter

    @property
    def name(self) -> str:
        return "github_create_issue"

    @property
    def description(self) -> str:
        return "Create GitHub issue. Params: title (str), body (str), labels (list)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        title = str(params.get("title", "")).strip()
        body = str(params.get("body", ""))
        labels_raw = params.get("labels", [])
        labels = [str(lbl) for lbl in labels_raw] if isinstance(labels_raw, list) else []

        if not title:
            return "Error: parameter 'title' wajib diisi."

        try:
            issue = _run_async(self.github.create_issue(title, body, labels or None))
        except (GitHubUnavailableError, GitHubAPIError) as exc:
            return f"GitHub error: {exc}"
        except Exception as exc:
            return f"Gagal membuat issue: {exc}"

        return f"Issue #{issue.number} dibuat: {issue.title}\n{issue.url}"  # type: ignore[union-attr]


@dataclass
class GitHubCommentAction:
    """Add a comment to a GitHub issue."""

    github: GitHubAdapter

    @property
    def name(self) -> str:
        return "github_comment"

    @property
    def description(self) -> str:
        return "Comment on GitHub issue. Params: number (int), body (str)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        number_raw = params.get("number")
        body = str(params.get("body", "")).strip()

        if number_raw is None:
            return "Error: parameter 'number' wajib diisi."
        try:
            number = int(number_raw)
        except (TypeError, ValueError):
            return f"Error: 'number' harus berupa integer, bukan {number_raw!r}."
        if not body:
            return "Error: parameter 'body' wajib diisi."

        try:
            _run_async(self.github.comment_issue(number, body))
        except (GitHubUnavailableError, GitHubAPIError) as exc:
            return f"GitHub error: {exc}"
        except Exception as exc:
            return f"Gagal menambah komentar: {exc}"

        return f"Komentar ditambahkan ke issue #{number}."


@dataclass
class GitHubListIssuesAction:
    """List GitHub issues."""

    github: GitHubAdapter

    @property
    def name(self) -> str:
        return "github_list_issues"

    @property
    def description(self) -> str:
        return "List open GitHub issues. Params: state (str, default 'open')"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        state = str(params.get("state", "open")).strip()
        if state not in {"open", "closed", "all"}:
            state = "open"

        try:
            issues = _run_async(self.github.list_issues(state=state))
        except (GitHubUnavailableError, GitHubAPIError) as exc:
            return f"GitHub error: {exc}"
        except Exception as exc:
            return f"Gagal mengambil issue list: {exc}"

        if not issues:
            return f"Tidak ada issue dengan state='{state}'."

        lines = [f"GitHub Issues ({state}):"]
        for issue in issues:  # type: ignore[union-attr]
            lines.append(f"  #{issue.number} [{issue.state}] {issue.title}")
        return "\n".join(lines)


@dataclass
class GitHubCloseIssueAction:
    """Close a GitHub issue."""

    github: GitHubAdapter

    @property
    def name(self) -> str:
        return "github_close_issue"

    @property
    def description(self) -> str:
        return "Close GitHub issue. Params: number (int), comment (str)"

    def execute(self, params: dict | None = None) -> str:
        params = params or {}
        number_raw = params.get("number")
        comment = str(params.get("comment", ""))

        if number_raw is None:
            return "Error: parameter 'number' wajib diisi."
        try:
            number = int(number_raw)
        except (TypeError, ValueError):
            return f"Error: 'number' harus berupa integer, bukan {number_raw!r}."

        try:
            _run_async(self.github.close_issue(number, comment))
        except (GitHubUnavailableError, GitHubAPIError) as exc:
            return f"GitHub error: {exc}"
        except Exception as exc:
            return f"Gagal menutup issue: {exc}"

        return f"Issue #{number} ditutup."


def register_github_ops(registry: ActionRegistry, github: GitHubAdapter) -> None:
    """Register all GitHub issue actions into *registry*."""
    actions = [
        GitHubCreateIssueAction(github=github),
        GitHubCommentAction(github=github),
        GitHubListIssuesAction(github=github),
        GitHubCloseIssueAction(github=github),
    ]

    risk_map: dict[str, str] = {
        "github_create_issue": "medium",
        "github_comment":      "low",
        "github_list_issues":  "low",
        "github_close_issue":  "medium",
    }

    for action in actions:
        risk = risk_map.get(action.name, "medium")
        registry.register(ActionMeta(
            name=action.name,
            description=action.description,
            risk_level=risk,
            requires_approval=False,
            handler=action.execute,
        ))
