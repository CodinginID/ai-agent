"""Output area helpers — append text + invalidate Application untuk redraw.

Single-threaded (asyncio loop prompt_toolkit) — tidak butuh lock.
"""

from __future__ import annotations

from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import FormattedText

from app.tui import _state


def println(style: str, text: str) -> None:
    _state.output.append((style, text + "\n"))
    if _state.app is not None:
        _state.app.invalidate()


def print_parts(parts: list[tuple[str, str]], newline: bool = True) -> None:
    _state.output.extend(parts)
    if newline:
        _state.output.append(("", "\n"))
    if _state.app is not None:
        _state.app.invalidate()


def clear_output() -> None:
    _state.output.clear()
    if _state.app is not None:
        _state.app.invalidate()


def get_output_text() -> FormattedText:
    return FormattedText(list(_state.output))


def get_output_cursor() -> Point:
    row = sum(t.count("\n") for _, t in _state.output)
    return Point(x=0, y=max(0, row))
