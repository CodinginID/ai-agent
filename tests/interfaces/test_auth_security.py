"""Auth hardening — admin fail-closed + email allowlist (Fase 0)."""

from __future__ import annotations

import dataclasses

import pytest
from fastapi import HTTPException

import app.interfaces.auth as auth
from app.config import load_settings


def _with(**kw: object):
    return dataclasses.replace(load_settings(), **kw)


def test_admin_token_empty_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "settings", _with(admin_token=""))
    with pytest.raises(HTTPException) as exc:
        auth._require_admin_token("Bearer x")
    assert exc.value.status_code == 503


def test_admin_token_valid_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "settings", _with(admin_token="s3cret"))
    auth._require_admin_token("Bearer s3cret")  # tidak raise


def test_admin_token_invalid_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "settings", _with(admin_token="s3cret"))
    with pytest.raises(HTTPException) as exc:
        auth._require_admin_token("Bearer wrong")
    assert exc.value.status_code == 401


def test_email_allowlist_empty_allows_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "settings", _with(allowed_emails=frozenset()))
    assert auth._email_allowed("anyone@example.com") is True


def test_email_allowlist_enforced_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth, "settings", _with(allowed_emails=frozenset({"ali@hamasmart.com"}))
    )
    assert auth._email_allowed("ali@hamasmart.com") is True
    assert auth._email_allowed("Ali@Hamasmart.com") is True  # case-insensitive
    assert auth._email_allowed("evil@example.com") is False
