"""Domain exceptions — satu tempat untuk semua error yang berasal dari domain logic."""

from __future__ import annotations


class AIProviderError(Exception):
    """AI provider gagal merespons atau mengembalikan hasil tidak valid."""


class ActionExecutionError(Exception):
    """Eksekusi action gagal (I/O error, subprocess error, dsb.)."""


class IntentParseError(Exception):
    """Gagal mem-parsing atau mengklasifikasi intent dari teks user."""
