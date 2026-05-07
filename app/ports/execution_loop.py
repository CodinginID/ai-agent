"""Port untuk ExecutionLoop — abstraksi agentic observe/think/execute/reflect cycle.

Use case menerima objek yang implement Protocol ini. Implementasi konkret ada di
``app/executor/loop.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol


class ExecutionLoopPort(Protocol):
    def run(self, prompt: str, history: str = "") -> Iterator[Any]: ...
