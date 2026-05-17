"""Capability registry — apa yang setiap agent BISA lakukan, dan apa yang setiap role BUTUHKAN.

Sumber kebenaran konstanta (per ``agent_id``), bukan per-device. Per-device
override bisa di-overlay lewat ``AgentIntegrationModel.capabilities['tags']``
kalau ke depan dibutuhkan (mis. user uninstall fitur tertentu di mesin
spesifik). Untuk sekarang, defaults sudah cukup.

Pure domain module — zero import dari adapter/framework.
"""

from __future__ import annotations

# ── Vocabulary ────────────────────────────────────────────────────────────────

KNOWN_CAPABILITY_TAGS: frozenset[str] = frozenset({
    "code",     # tulis / edit source code
    "review",   # kritik kode atau dokumen, surface masalah
    "reason",   # break down problem, design arsitektur tingkat tinggi
    "write",    # produksi prosa, dokumentasi, copy
    "browse",   # akses web (future capability — belum di-wire)
    "debate",   # diskusi multi-ronde (future)
    "ask",      # tanya klarifikasi ke user secara interaktif (future)
})


# ── Defaults per agent ────────────────────────────────────────────────────────

DEFAULT_AGENT_CAPABILITIES: dict[str, frozenset[str]] = {
    "codex":    frozenset({"code"}),
    "claude":   frozenset({"code", "review", "reason", "write"}),
    "glm":      frozenset({"code", "reason", "write"}),
    "deepseek": frozenset({"code", "reason"}),
    "qwen":     frozenset({"code", "reason", "write"}),
}


# ── Role requirements ─────────────────────────────────────────────────────────

ROLE_REQUIRED_CAPABILITIES: dict[str, frozenset[str]] = {
    "engineer":  frozenset({"code"}),
    "reviewer":  frozenset({"code", "review"}),
    "architect": frozenset({"reason"}),
}


# ── Errors ────────────────────────────────────────────────────────────────────

class CapabilityMismatchError(ValueError):
    """Agent tidak punya cukup capability untuk role yang di-assign."""


class UnknownRoleError(ValueError):
    """Role tidak terdaftar di ``ROLE_REQUIRED_CAPABILITIES``."""


# ── API ───────────────────────────────────────────────────────────────────────

def capabilities_for_agent(agent_id: str) -> frozenset[str]:
    """Return capability set untuk agent. Empty kalau agent_id tidak dikenal."""
    return DEFAULT_AGENT_CAPABILITIES.get(agent_id, frozenset())


def required_for_role(role: str) -> frozenset[str]:
    """Return required-capability set untuk role.

    Raise ``UnknownRoleError`` kalau role tidak terdaftar — supaya typo
    di TUI/Telegram tidak silently lolos.
    """
    if role not in ROLE_REQUIRED_CAPABILITIES:
        known = ", ".join(sorted(ROLE_REQUIRED_CAPABILITIES))
        raise UnknownRoleError(
            f"Role '{role}' tidak dikenal. Pilih salah satu: {known}"
        )
    return ROLE_REQUIRED_CAPABILITIES[role]


def validate_role_assignment(agent_id: str, role: str) -> None:
    """Validate agent capable enough untuk role.

    Raise:
        ``UnknownRoleError`` kalau role bukan role yang dikenal.
        ``CapabilityMismatchError`` kalau agent kurang capability.
    """
    required = required_for_role(role)
    have = capabilities_for_agent(agent_id)
    missing = required - have
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise CapabilityMismatchError(
            f"Agent '{agent_id}' tidak punya kapabilitas {{{missing_str}}} "
            f"yang dibutuhkan role '{role}'. "
            f"Agent ini bisa: {sorted(have) or '(tidak dikenal)'}."
        )
