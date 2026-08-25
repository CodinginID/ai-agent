"""Log redaction — strip sensitive values before writing to log output.

Patterns matched (case-insensitive where appropriate):
- Anthropic API key: ``sk-ant-...``
- GitHub token: ``ghp_...``
- Telegram bot token: ``<digits>:AA...``
- Google OAuth client secret: JSON ``"client_secret": "<value>"`` blocks
- Generic API key/env var: ``<NAME>=<value>`` where ``NAME`` is a known secret key
"""
from __future__ import annotations

import re

_REPLACEMENT = "***REDACTED***"

# Compile once at module load for performance.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
        _REPLACEMENT,
    ),
    (
        re.compile(r"ghp_[A-Za-z0-9_\-]{20,}"),
        _REPLACEMENT,
    ),
    (
        re.compile(r"\d{6,}:AA[A-Za-z0-9_\-]{20,}"),
        _REPLACEMENT,
    ),
    (
        re.compile(r'"client_secret"\s*:\s*"([^"]*)"'),
        f'"client_secret": "{_REPLACEMENT}"',
    ),
    (
        re.compile(r"(ANTHROPIC_API_KEY|GITHUB_TOKEN|TELEGRAM_BOT_TOKEN|ADMIN_TOKEN|GOOGLE_CLIENT_SECRET|WEBHOOK_SECRET|DATABASE_URL)\s*=\s*\S+", re.IGNORECASE),
        rf"\1={_REPLACEMENT}",
    ),
)


def redact_secrets(text: str) -> str:
    """Return *text* with every known secret pattern replaced by ``***REDACTED***``.

    The function is safe to call on already-redacted text (idempotent) and on
    ``None`` (returns the empty string).
    """
    if not text:
        return ""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
