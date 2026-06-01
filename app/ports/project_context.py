from typing import Protocol


class ProjectContextProvider(Protocol):
    """Return a bounded, prompt-ready summary of a namespace's project context.

    Returns an empty string when there is nothing to inject.
    """

    def build_context(self, namespace: str, max_chars: int = ...) -> str: ...
