"""Runtime tool registry and dispatch helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from autoharness.errors import AutoHarnessError, ErrorCode


class ToolHandler(Protocol):
    def __call__(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """Execute a Runtime tool and return an object result."""


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    handler: ToolHandler


class ToolHost:
    """Small in-process Tool Host used by Runtime dispatch."""

    def __init__(self, tools: Mapping[str, ToolHandler | Callable[[Mapping[str, Any]], Mapping[str, Any]]] | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        for name, handler in (tools or {}).items():
            self.register(name, handler)

    def register(self, name: str, handler: ToolHandler | Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> None:
        if not name:
            raise AutoHarnessError(ErrorCode.SCHEMA_INVALID, "tool name must be non-empty")
        self._tools[name] = ToolDefinition(name=name, handler=handler)

    def has(self, name: str) -> bool:
        return name in self._tools

    def dispatch(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise AutoHarnessError(ErrorCode.TOOL_NOT_FOUND, f"tool not found: {name}")
        result = self._tools[name].handler(deepcopy(dict(arguments)))
        if not isinstance(result, dict):
            raise AutoHarnessError(
                ErrorCode.SCHEMA_INVALID,
                "tool output must be an object",
            )
        return deepcopy(result)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))
