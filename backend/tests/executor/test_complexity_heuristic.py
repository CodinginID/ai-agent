"""Tests for the complexity heuristic that routes requests to ExecutionLoop."""

from __future__ import annotations

import pytest

from app.domain.use_cases import _is_complex_request

# ── Simple requests — should NOT trigger the loop ────────────────────────────

@pytest.mark.parametrize("text,intent", [
    ("cek memory", "memory"),
    ("docker ps", "docker_ps"),
    ("git status", "git_status"),
    ("cek disk", "disk"),
    ("server status", "server_status"),
    ("whoami", "whoami"),
    ("list files", "list_files"),
    ("docker images", "docker_images"),
    ("docker stats", "docker_stats"),
    ("docker logs", "docker_logs"),
])
def test_simple_requests_not_complex(text: str, intent: str) -> None:
    assert _is_complex_request(text, intent) is False


# ── Complex requests — should trigger the loop ────────────────────────────────

@pytest.mark.parametrize("text,intent", [
    ("kenapa docker crash?", "unknown"),
    ("why is the server slow?", "unknown"),
    ("analisa penggunaan disk terakhir", "unknown"),
    ("debug masalah di container bot", "unknown"),
    ("apa yang terjadi dengan redis?", "unknown"),
    ("bandingkan memory sekarang vs kemarin", "unknown"),
    ("diagnose the CPU spike issue", "unknown"),
    ("investigate log errors in docker", "unknown"),
    ("what went wrong with the deployment", "unknown"),
    ("step by step check server health", "unknown"),
    ("read file /var/log/app.log and explain errors", "unknown"),
    ("compare git diff before and after deploy", "unknown"),
])
def test_complex_requests_are_complex(text: str, intent: str) -> None:
    assert _is_complex_request(text, intent) is True


# ── Unknown intent always routes to loop ─────────────────────────────────────

def test_unknown_intent_always_complex() -> None:
    assert _is_complex_request("some ambiguous question", "unknown") is True


# ── Simple intent always bypasses loop even if text looks complex ─────────────

def test_simple_intent_bypasses_loop_even_with_complex_text() -> None:
    # Intent was confidently classified as memory — use fast path.
    assert _is_complex_request("kenapa memory penuh?", "memory") is False
    assert _is_complex_request("why is disk usage high?", "disk") is False
