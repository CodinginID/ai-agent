from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class ActionProtocol(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    def execute(self, params: dict[str, Any] | None = None) -> str: ...


@dataclass(frozen=True)
class ActionMeta:
    name: str
    description: str
    risk_level: str          # "low" | "medium" | "high"
    requires_approval: bool
    handler: Callable[[dict[str, Any] | None], str]


class ActionRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, ActionMeta] = {}

    def register(self, meta: ActionMeta) -> None:
        self._actions[meta.name] = meta

    def get(self, name: str) -> ActionMeta | None:
        return self._actions.get(name)

    def execute(self, name: str, context: dict[str, Any] | None = None) -> str:
        meta = self.get(name)
        if meta is None:
            raise KeyError(f"Action '{name}' tidak terdaftar di registry")
        return meta.handler(context)

    def names(self) -> frozenset[str]:
        return frozenset(self._actions)

    def list_all(self) -> list[ActionMeta]:
        return sorted(self._actions.values(), key=lambda a: (a.risk_level, a.name))
