"""Unit tests for app/adapters/github.py — HTTP calls are mocked via unittest.mock."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.github import (
    GitHubAPIError,
    GitHubAdapter,
    GitHubIssue,
    GitHubUnavailableError,
)


# ── Constructor validation ─────────────────────────────────────────────────────

def test_init_raises_when_token_empty() -> None:
    with pytest.raises(GitHubUnavailableError, match="GITHUB_TOKEN"):
        GitHubAdapter(token="", repo="owner/repo")


def test_init_raises_when_repo_missing_slash() -> None:
    with pytest.raises(GitHubUnavailableError, match="owner/repo"):
        GitHubAdapter(token="tok", repo="just-name")


def test_init_raises_when_repo_empty() -> None:
    with pytest.raises(GitHubUnavailableError):
        GitHubAdapter(token="tok", repo="")


def test_init_succeeds_with_valid_args() -> None:
    adapter = GitHubAdapter(token="ghp_abc", repo="acme/project")
    assert adapter._repo == "acme/project"


# ── _headers ──────────────────────────────────────────────────────────────────

def test_headers_include_bearer_token() -> None:
    adapter = GitHubAdapter(token="ghp_secret", repo="owner/repo")
    headers = adapter._headers()
    assert headers["Authorization"] == "Bearer ghp_secret"
    assert "application/vnd.github" in headers["Accept"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_response(status_code: int, data: object) -> httpx.Response:
    """Build a fake httpx.Response with a JSON body."""
    import json as _json
    content = _json.dumps(data).encode()
    return httpx.Response(status_code, content=content)


def _patch_async_client(mock_method: str, response: httpx.Response):
    """Context manager that patches httpx.AsyncClient.<mock_method> to return *response*."""
    return patch(
        f"httpx.AsyncClient.{mock_method}",
        new_callable=AsyncMock,
        return_value=response,
    )


# ── create_issue ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_issue_returns_github_issue() -> None:
    resp = _make_response(201, {
        "number": 42,
        "title": "Bug found",
        "html_url": "https://g.co/42",
        "state": "open",
    })
    with _patch_async_client("post", resp):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        issue = await adapter.create_issue("Bug found", "Details here")

    assert isinstance(issue, GitHubIssue)
    assert issue.number == 42
    assert issue.url == "https://g.co/42"
    assert issue.state == "open"


@pytest.mark.asyncio
async def test_create_issue_raises_on_api_error() -> None:
    resp = _make_response(422, {"message": "Validation Failed"})
    with _patch_async_client("post", resp):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        with pytest.raises(GitHubAPIError, match="Validation Failed"):
            await adapter.create_issue("Bad title")


@pytest.mark.asyncio
async def test_create_issue_sends_labels_when_provided() -> None:
    resp = _make_response(201, {
        "number": 1,
        "title": "t",
        "html_url": "u",
        "state": "open",
    })
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp) as mock_post:
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        await adapter.create_issue("t", labels=["bug", "urgent"])

    _, kwargs = mock_post.call_args
    assert "bug" in kwargs["json"]["labels"]


# ── list_issues ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_issues_returns_list() -> None:
    resp = _make_response(200, [
        {"number": 1, "title": "Issue one", "html_url": "https://g.co/1", "state": "open"},
        {"number": 2, "title": "Issue two", "html_url": "https://g.co/2", "state": "open"},
    ])
    with _patch_async_client("get", resp):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        issues = await adapter.list_issues()

    assert len(issues) == 2
    assert issues[0].number == 1
    assert issues[1].title == "Issue two"


@pytest.mark.asyncio
async def test_list_issues_empty_returns_empty_list() -> None:
    resp = _make_response(200, [])
    with _patch_async_client("get", resp):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        issues = await adapter.list_issues()

    assert issues == []


@pytest.mark.asyncio
async def test_list_issues_raises_on_unauthorized() -> None:
    resp = _make_response(401, {"message": "Bad credentials"})
    with _patch_async_client("get", resp):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        with pytest.raises(GitHubAPIError, match="Bad credentials"):
            await adapter.list_issues()


# ── comment_issue ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_comment_issue_succeeds() -> None:
    resp = _make_response(201, {"id": 99})
    with _patch_async_client("post", resp):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        # Should not raise
        await adapter.comment_issue(5, "Looks good!")


@pytest.mark.asyncio
async def test_comment_issue_raises_on_error() -> None:
    resp = _make_response(404, {"message": "Not Found"})
    with _patch_async_client("post", resp):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        with pytest.raises(GitHubAPIError, match="Not Found"):
            await adapter.comment_issue(9999, "comment")


# ── close_issue ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_close_issue_without_comment() -> None:
    resp = _make_response(200, {"number": 7, "state": "closed"})
    with _patch_async_client("patch", resp):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        await adapter.close_issue(7)


@pytest.mark.asyncio
async def test_close_issue_with_comment_posts_comment_first() -> None:
    comment_resp = _make_response(201, {"id": 1})
    close_resp = _make_response(200, {"number": 8, "state": "closed"})

    call_count = 0
    posted_bodies: list[dict] = []

    async def fake_post(url: str, **kwargs: object) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        posted_bodies.append(kwargs.get("json", {}))
        return comment_resp

    async def fake_patch(url: str, **kwargs: object) -> httpx.Response:
        return close_resp

    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=fake_post),
        patch("httpx.AsyncClient.patch", new_callable=AsyncMock, side_effect=fake_patch),
    ):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        await adapter.close_issue(8, comment="Fixed in #10.")

    assert call_count == 1  # comment was posted
    assert "Fixed in #10." in posted_bodies[0].get("body", "")


# ── update_issue_label ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_issue_label_succeeds() -> None:
    resp = _make_response(200, [{"name": "bug"}])
    with _patch_async_client("put", resp):
        adapter = GitHubAdapter(token="tok", repo="owner/repo")
        await adapter.update_issue_label(3, ["bug"])
