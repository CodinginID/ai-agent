"""Generic input validators — length, path traversal, shell injection hints."""

from __future__ import annotations

import re

_PATH_TRAVERSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.\.[\\/]"),           # ../ or ..\
    re.compile(r"\.\./"),               # ../ explicit (redundant safety net)
    re.compile(r"\"\.\."),              # ".." followed by quote
)


def validate_input(text: str, max_length: int = 10000) -> str | None:
    """Validate *text* against common input-attack patterns.

    Returns ``None`` when valid, or an error message string when rejected.

    Checks performed:
    1. Length -- text must be at most ``max_length`` characters.
    2. Path traversal -- rejects ``../`` and ``..\\`` substrings.
    """
    if not isinstance(text, str):
        return "Input harus berupa string."

    stripped = text.strip()

    if len(stripped) == 0:
        return "Input kosong."

    if len(stripped) > max_length:
        return f"Pesan terlalu panjang (max {max_length} karakter)"

    for pattern in _PATH_TRAVERSAL_PATTERNS:
        if pattern.search(stripped):
            return "Input mengandung path traversal yang tidak diizinkan."

    return None
