"""Port untuk structured audit logging.

Domain layer (``HandleMessageUseCase``) panggil ``log`` untuk mencatat event
penting selama menangani request. Implementasi konkret (JSON Lines file,
stdout, atau remote sink) ada di ``app/adapters/audit.py`` dan di-inject
lewat composition root.
"""

from __future__ import annotations

from typing import Any, Protocol


class AuditLogger(Protocol):
    def log(self, event: str, trace_id: str, **fields: Any) -> None: ...
