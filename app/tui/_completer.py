"""Tab completer — slash commands + email autocomplete untuk /admin-logout."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from prompt_toolkit.completion import Completer, Completion

if TYPE_CHECKING:
    from prompt_toolkit.document import Document

ALL_COMMANDS = [
    "/help", "/login", "/logout", "/me", "/pair-telegram",
    "/status", "/users", "/admin-logout ",
    "/logs", "/logs -f", "/shell", "/clear", "/quit",
]


class TuiCompleter(Completer):
    def __init__(self) -> None:
        self._emails: list[str] = []

    def set_emails(self, emails: list[str]) -> None:
        self._emails = emails

    def get_completions(
        self, document: Document, complete_event: object,
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        if text.startswith("/admin-logout "):
            prefix = text[len("/admin-logout "):]
            for email in self._emails:
                if email.lower().startswith(prefix.lower()):
                    yield Completion(email[len(prefix):], display=email)
        elif text.startswith("/"):
            for cmd in ALL_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd[len(text):], display=cmd.strip())
