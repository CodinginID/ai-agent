"""Port for GitHub Issues — task records for the orchestrator task runner.

The task runner uses an issue as the durable record of a multi-step task:
create on start, comment per step (attempt log), close on completion. Depending
on a Protocol (not the concrete ``GitHubAdapter``) keeps the orchestrator
testable and hexagonal-clean.
"""

from __future__ import annotations

from typing import Protocol

from app.adapters.github import GitHubIssue


class GitHubIssuesPort(Protocol):
    async def create_issue(
        self, title: str, body: str = "", labels: list[str] | None = None,
    ) -> GitHubIssue: ...

    async def comment_issue(self, issue_number: int, body: str) -> None: ...

    async def close_issue(self, issue_number: int, comment: str = "") -> None: ...
