from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from app.intents.schemas import (
    HIGH_RISK,
    KNOWN_INTENTS,
    MEDIUM_RISK,
    Intent,
)

_GREETING_WORDS: frozenset[str] = frozenset({
    "hi", "hai", "halo", "hello", "hey",
    "pagi", "siang", "sore", "malam",
    "assalamualaikum", "assalamu'alaikum",
})

_QUESTION_PREFIXES = (
    "apa itu", "apa maksud", "jelaskan", "explain",
    "what is", "what are", "bagaimana cara", "gimana cara",
    "kenapa", "mengapa", "why", "how to",
    "bantu", "bisa bantu", "bisa jelaskan",
    "tolong bantu", "tolong jelaskan",
)

# Frasa percakapan eksplisit — kalau ada, route ke chat tanpa cek action keyword.
# Mencegah substring false-positive (mis. "diskusi" mengandung "disk").
_CHAT_PHRASES = (
    "ingin diskusi", "mau diskusi", "bisa diskusi", "kita diskusi",
    "ingin tanya", "mau tanya", "boleh tanya",
    "saya pengen", "saya ingin", "saya mau",
    "kita ingin", "kita pengen", "kita mau",
    "menurut kamu", "menurut anda",
    "let's talk", "let's discuss",
    "ngobrol", "diskusi", "ngediskusiin",
    "ada saran", "kasih saran", "kasih masukan", "kasih tips",
)

_ACTION_KEYWORDS = (
    "cek", "check", "lihat", "tampilkan", "show", "status",
    "jalan", "running", "list", "daftar",
    "usage", "penggunaan", "stats", "statistik",
)


def _has_word(text: str, *words: str) -> bool:
    """Word-boundary match — hindari substring false-positive (disk vs diskusi)."""
    for w in words:
        if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE):
            return True
    return False


def _has_phrase(text: str, *phrases: str) -> bool:
    return any(p in text for p in phrases)

_JSON_PROMPT = """\
You are a strict JSON intent parser for a private Telegram server admin bot.

Available intents (pick exactly one):
- server_status   : check server health, uptime, CPU, RAM, load, disk summary
- memory          : check RAM or swap usage
- disk            : check disk usage
- processes       : show active processes
- docker_ps       : list running Docker containers
- docker_images   : list Docker images
- docker_stats    : show Docker container resource usage
- docker_restart  : restart a Docker container  [MEDIUM RISK]
- docker_logs     : show Docker container logs
- git_status      : show git repository status
- git_pull        : pull latest code from remote  [MEDIUM RISK]
- list_files      : list files in project directory
- whoami          : show bot user, working directory, and hostname
- chat            : greetings, general conversation, explanations, or unrelated questions
- unknown         : does not match any available action

Rules:
- requires_approval MUST be true for: docker_restart, git_pull, deploy_restart, run_command
- confidence: float 0.0-1.0
- reason: short English sentence explaining the choice
- parameters: empty object unless intent needs specific args (e.g. container_name)
- project_id: use the value provided below

project_id: {project_id}

User input:
{user_text}

Respond ONLY with valid minified JSON — no explanation, no markdown:
{{"intent":"server_status","project_id":"{project_id}","confidence":0.94,"requires_approval":false,"parameters":{{}},"reason":"User asks about server health"}}"""


def _is_greeting(text: str) -> bool:
    return text.lower().strip(" .,!?\n\t") in _GREETING_WORDS


def _looks_like_chat(text: str) -> bool:
    normalized = text.lower().strip()
    is_question = normalized.endswith("?") or any(
        normalized.startswith(p) for p in _QUESTION_PREFIXES
    )
    has_action = any(kw in normalized for kw in _ACTION_KEYWORDS)
    return is_question and not has_action


def _make(
    intent: str,
    project_id: str,
    confidence: float,
    requires_approval: bool,
    reason: str,
    parameters: dict[str, Any] | None = None,
) -> Intent:
    return Intent(
        intent=intent,
        project_id=project_id,
        confidence=confidence,
        requires_approval=requires_approval,
        parameters=parameters or {},
        reason=reason,
    )


def _parse_local(text: str, project_id: str) -> Intent | None:
    t = text.lower().strip()

    # Frasa percakapan eksplisit menang duluan — supaya "ingin diskusi" tidak
    # ke-trigger "disk" via substring match.
    if _has_phrase(t, *_CHAT_PHRASES):
        return _make("chat", project_id, 1.0, False, "Conversation phrase detected")

    if _is_greeting(t) or _looks_like_chat(t):
        return _make("chat", project_id, 1.0, False, "Greeting or general chat")

    if _has_word(t, "docker", "container"):
        if _has_word(t, "image", "images"):
            return _make("docker_images", project_id, 0.95, False, "Docker images query")
        if _has_word(t, "stats", "statistik", "resource"):
            return _make("docker_stats", project_id, 0.95, False, "Docker stats query")
        if _has_word(t, "restart", "ulang", "stop", "start"):
            return _make("docker_restart", project_id, 0.9, True, "Docker restart — needs approval")
        if _has_word(t, "log", "logs"):
            return _make("docker_logs", project_id, 0.9, False, "Docker logs query")
        return _make("docker_ps", project_id, 0.95, False, "Docker container list")

    if _has_word(t, "git"):
        if _has_word(t, "pull"):
            return _make("git_pull", project_id, 0.9, True, "Git pull — needs approval")
        return _make("git_status", project_id, 0.95, False, "Git status query")

    if _has_word(t, "ram", "memory", "memori", "swap"):
        return _make("memory", project_id, 0.95, False, "Memory usage query")

    if _has_word(t, "disk", "storage", "penyimpanan", "df"):
        return _make("disk", project_id, 0.95, False, "Disk usage query")

    if _has_word(t, "process", "processes", "proses", "ps", "top"):
        return _make("processes", project_id, 0.9, False, "Process list query")

    if _has_word(t, "whoami", "hostname") or _has_phrase(t, "user bot", "working dir"):
        return _make("whoami", project_id, 0.95, False, "Identity query")

    if _has_phrase(t, "list file", "lihat file") or _has_word(t, "ls"):
        return _make("list_files", project_id, 0.9, False, "File listing")

    if _has_word(t, "status", "uptime", "health", "sehat", "server", "load", "cpu"):
        return _make("server_status", project_id, 0.9, False, "Server status query")

    return None


class IntentParser:
    def __init__(self, qwen_caller: Callable[[str], str]) -> None:
        self._call_qwen = qwen_caller

    def parse(self, text: str, project_id: str = "default") -> Intent:
        local = _parse_local(text, project_id)
        if local is not None:
            return local

        try:
            raw = self._call_qwen(
                _JSON_PROMPT.format(user_text=text, project_id=project_id)
            )
            return self._extract(raw, project_id)
        except Exception:
            return _make("unknown", project_id, 0.0, False, "AI call failed")

    def _extract(self, raw: str, project_id: str) -> Intent:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return _make("unknown", project_id, 0.0, False, "AI returned no JSON")

        try:
            data: dict[str, Any] = json.loads(match.group())
        except json.JSONDecodeError:
            return _make("unknown", project_id, 0.0, False, "AI returned invalid JSON")

        intent_name = str(data.get("intent", "unknown"))
        if intent_name not in KNOWN_INTENTS:
            intent_name = "unknown"

        requires_approval = bool(data.get("requires_approval", False))
        if intent_name in MEDIUM_RISK | HIGH_RISK:
            requires_approval = True

        return Intent(
            intent=intent_name,
            project_id=str(data.get("project_id", project_id)),
            confidence=float(data.get("confidence", 0.5)),
            requires_approval=requires_approval,
            parameters=dict(data.get("parameters") or {}),
            reason=str(data.get("reason", "")),
        )
