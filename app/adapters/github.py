"""GitHub Issues adapter — create/update/close issues via GitHub REST API.

Requires:
- GITHUB_TOKEN: Personal Access Token or fine-grained token with issues:write scope
- GITHUB_REPO: repository in ``owner/repo`` format
- ENABLE_GITHUB: must be ``true`` for the adapter to be active
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class GitHubUnavailableError(Exception):
    """GitHub API is not configured or not reachable."""


class GitHubAPIError(Exception):
    """GitHub API returned an unexpected error response."""


@dataclass(frozen=True)
class GitHubIssue:
    number: int
    title: str
    url: str
    state: str


class GitHubAdapter:
    """Thin async wrapper around the GitHub Issues REST API."""

    _BASE_URL: str = "https://api.github.com"

    def __init__(self, token: str, repo: str) -> None:
        if not token:
            raise GitHubUnavailableError("GITHUB_TOKEN tidak diisi.")
        if not repo or "/" not in repo:
            raise GitHubUnavailableError(
                "GITHUB_REPO harus dalam format 'owner/repo'."
            )
        self._token = token
        self._repo = repo

    # ── helpers ───────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _issues_url(self, path: str = "") -> str:
        base = f"{self._BASE_URL}/repos/{self._repo}/issues"
        return f"{base}{path}" if path else base

    def _raise_for_status(self, resp: httpx.Response, context: str) -> None:
        if resp.is_error:
            try:
                message = resp.json().get("message", resp.text)
            except Exception:
                message = resp.text
            raise GitHubAPIError(
                f"{context} gagal (HTTP {resp.status_code}): {message}"
            )

    # ── public API ────────────────────────────────────────────────────────────

    async def create_issue(
        self,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
    ) -> GitHubIssue:
        """Create a new GitHub issue."""
        payload: dict[str, object] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._issues_url(),
                headers=self._headers(),
                json=payload,
                timeout=30,
            )

        self._raise_for_status(resp, "create_issue")
        data = resp.json()
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            url=data["html_url"],
            state=data["state"],
        )

    async def comment_issue(self, issue_number: int, body: str) -> None:
        """Add a comment to an issue."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._issues_url(f"/{issue_number}/comments"),
                headers=self._headers(),
                json={"body": body},
                timeout=30,
            )
        self._raise_for_status(resp, "comment_issue")

    async def close_issue(self, issue_number: int, comment: str = "") -> None:
        """Close an issue, optionally adding a final comment first."""
        if comment:
            await self.comment_issue(issue_number, comment)

        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                self._issues_url(f"/{issue_number}"),
                headers=self._headers(),
                json={"state": "closed"},
                timeout=30,
            )
        self._raise_for_status(resp, "close_issue")

    async def list_issues(
        self,
        state: str = "open",
        labels: list[str] | None = None,
        limit: int = 20,
    ) -> list[GitHubIssue]:
        """List issues filtered by state and optional labels."""
        params: dict[str, str] = {
            "state": state,
            "per_page": str(min(limit, 100)),
        }
        if labels:
            params["labels"] = ",".join(labels)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self._issues_url(),
                headers=self._headers(),
                params=params,
                timeout=30,
            )

        self._raise_for_status(resp, "list_issues")
        return [
            GitHubIssue(
                number=item["number"],
                title=item["title"],
                url=item["html_url"],
                state=item["state"],
            )
            for item in resp.json()
        ]

    async def update_issue_label(
        self, issue_number: int, labels: list[str]
    ) -> None:
        """Replace all labels on an issue."""
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                self._issues_url(f"/{issue_number}/labels"),
                headers=self._headers(),
                json={"labels": labels},
                timeout=30,
            )
        self._raise_for_status(resp, "update_issue_label")


class NullGitHubAdapter:
    """In-memory issues adapter — task tracking tanpa GitHub (mode portable/mock).

    Implements ``GitHubIssuesPort`` sehingga ``TaskRunner`` tetap jalan saat
    GITHUB_TOKEN/REPO belum diisi: task tetap didekomposisi & didispatch ke
    pasukan, hanya jejak issue-nya lokal (tidak ada sumber kebenaran eksternal).
    """

    def __init__(self) -> None:
        self._counter = itertools.count(1)

    async def create_issue(
        self, title: str, body: str = "", labels: list[str] | None = None,
    ) -> GitHubIssue:
        number = next(self._counter)
        logger.info("null-github: create_issue #%d %r", number, title[:60])
        return GitHubIssue(
            number=number,
            title=title,
            url=f"local://task/{number}",
            state="open",
        )

    async def comment_issue(self, issue_number: int, body: str) -> None:
        logger.debug("null-github: comment #%d %r", issue_number, body[:80])

    async def close_issue(self, issue_number: int, comment: str = "") -> None:
        logger.info("null-github: close_issue #%d", issue_number)
