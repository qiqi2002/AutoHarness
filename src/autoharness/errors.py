"""Stable runtime error codes."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    SCHEMA_INVALID = "E_SCHEMA_INVALID"
    ACTION_NOT_ALLOWED = "E_ACTION_NOT_ALLOWED"
    AGENT_NOT_FOUND = "E_AGENT_NOT_FOUND"
    TOOL_NOT_FOUND = "E_TOOL_NOT_FOUND"
    TEMP_BUFFER_LOCKED = "E_TEMP_BUFFER_LOCKED"
    IDEMPOTENCY_CONFLICT = "E_IDEMPOTENCY_CONFLICT"


class AutoHarnessError(Exception):
    """Error raised by protocol validation or runtime guards."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
