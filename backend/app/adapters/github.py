"""GitHub Issues adapter — create/update/close issues via GitHub REST API.

Requires:
- GITHUB_TOKEN: Personal Access Token or fine-grained token with issues:write scope
- GITHUB_REPO: repository in ``owner/repo`` format
- ENABLE_GITHUB: must be ``true`` for the adapter to be active

Retry policy (internal): 3x retries, 2s / 4s / 8s backoff + jitter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.safety.redact import redact_secrets

log = logging.getLogger(__name__)


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
            log.debug(
                "github request failed: url=%s status=%d context=%s",
                redact_secrets(resp.url),
                resp.status_code,
                context,
            )
            raise GitHubAPIError(
                f"{context} gagal (HTTP {resp.status_code}): {redact_secrets(message)}"
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

        from app.adapters.retry import retry_async

        return await retry_async(
            self._async_post_issue,
            max_retries=3,
            base_delay=2.0,
            max_delay=8.0,
            jitter=True,
        )(self._issues_url(), self._headers(), payload)

    async def _async_post_issue(self, url: str, headers: dict[str, str], payload: dict[str, object]) -> httpx.Response:
        """Internal helper: async POST to issues URL with retry."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=30,
            )
        self._raise_for_status(resp, "create_issue")
        return resp

    async def comment_issue(self, issue_number: int, body: str) -> None:
        """Add a comment to an issue."""
        from app.adapters.retry import retry_async

        await retry_async(
            self._async_post_issue,
            max_retries=3,
            base_delay=2.0,
            max_delay=8.0,
            jitter=True,
        )(self._issues_url(f"/{issue_number}/comments"), self._headers(), {"body": body})

    async def close_issue(self, issue_number: int, comment: str = "") -> None:
        """Close an issue, optionally adding a final comment first."""
        if comment:
            await self.comment_issue(issue_number, comment)

        from app.adapters.retry import retry_async

        async def _async_patch_issue(url: str, headers: dict[str, str], payload: dict[str, object]) -> httpx.Response:
            """Internal helper: async PATCH to issues URL with retry."""
            async with httpx.AsyncClient() as client:
                resp = await client.patch(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
            self._raise_for_status(resp, "close_issue")
            return resp

        await retry_async(
            _async_patch_issue,
            max_retries=3,
            base_delay=2.0,
            max_delay=8.0,
            jitter=True,
        )(self._issues_url(f"/{issue_number}"), self._headers(), {"state": "closed"})

    async def list_issues(
        self,
        state: str = "open",
        labels: list[str] | None = None,
        limit: int = 20,
    ) -> list[GitHubIssue]:
        """List issues filtered by state and optional labels."""
        from app.adapters.retry import retry_async

        params: dict[str, str] = {
            "state": state,
            "per_page": str(min(limit, 100)),
        }
        if labels:
            params["labels"] = ",".join(labels)

        return await retry_async(
            self._async_get_issues,
            max_retries=3,
            base_delay=2.0,
            max_delay=8.0,
            jitter=True,
        )(self._issues_url(), self._headers(), params)

    async def _async_get_issues(self, url: str, headers: dict[str, str], params: dict[str, str]) -> list[GitHubIssue]:
        """Internal helper: async GET issues with retry."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers=headers,
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
        from app.adapters.retry import retry_async

        async def _async_put_labels(url: str, headers: dict[str, str], payload: dict[str, object]) -> httpx.Response:
            """Internal helper: async PUT labels with retry."""
            async with httpx.AsyncClient() as client:
                resp = await client.put(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
            self._raise_for_status(resp, "update_issue_label")
            return resp

        await retry_async(
            _async_put_labels,
            max_retries=3,
            base_delay=2.0,
            max_delay=8.0,
            jitter=True,
        )(self._issues_url(f"/{issue_number}/labels"), self._headers(), {"labels": labels})
