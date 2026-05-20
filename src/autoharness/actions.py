"""Action envelope validation for the M1 protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from autoharness.errors import AutoHarnessError, ErrorCode


ACTION_TYPES = {
    "create_agent",
    "update_agent",
    "update_plan",
    "dispatch",
    "accept_output",
    "finish",
}

ENVELOPE_KEYS = {
    "schema_version",
    "action_id",
    "trace_id",
    "action_type",
    "payload",
}


@dataclass(frozen=True)
class Action:
    schema_version: str
    action_id: str
    trace_id: str
    action_type: str
    payload: dict[str, Any]


def validate_action(raw: Mapping[str, Any]) -> Action:
    """Validate a raw Action envelope and return a normalized Action."""

    if not isinstance(raw, Mapping):
        _invalid("action must be a JSON object")

    _require_exact_keys(raw, ENVELOPE_KEYS, "action")

    schema_version = raw["schema_version"]
    action_id = raw["action_id"]
    trace_id = raw["trace_id"]
    action_type = raw["action_type"]
    payload = raw["payload"]

    if schema_version != "1.0":
        _invalid("schema_version must be '1.0'")
    _require_uuid(action_id, "action_id")
    _require_uuid(trace_id, "trace_id")
    if action_type not in ACTION_TYPES:
        _invalid(f"unknown action_type: {action_type!r}")
    if not isinstance(payload, dict):
        _invalid("payload must be an object")

    _validate_payload(action_type, payload)

    return Action(
        schema_version=schema_version,
        action_id=action_id,
        trace_id=trace_id,
        action_type=action_type,
        payload=dict(payload),
    )


def _validate_payload(action_type: str, payload: Mapping[str, Any]) -> None:
    validators = {
        "create_agent": _validate_create_agent,
        "update_agent": _validate_update_agent,
        "update_plan": _validate_update_plan,
        "dispatch": _validate_dispatch,
        "accept_output": _validate_accept_output,
        "finish": _validate_finish,
    }
    validators[action_type](payload)


def _validate_create_agent(payload: Mapping[str, Any]) -> None:
    _require_exact_keys(payload, {"name", "role", "prompt", "io_schema"}, "create_agent payload")
    _require_non_empty_string(payload["name"], "name")
    _require_non_empty_string(payload["role"], "role")
    _require_non_empty_string(payload["prompt"], "prompt")
    _require_object(payload["io_schema"], "io_schema")


def _validate_update_agent(payload: Mapping[str, Any]) -> None:
    _require_exact_keys(payload, {"name", "new_prompt", "reason"}, "update_agent payload")
    _require_non_empty_string(payload["name"], "name")
    _require_non_empty_string(payload["new_prompt"], "new_prompt")
    _require_non_empty_string(payload["reason"], "reason")


def _validate_update_plan(payload: Mapping[str, Any]) -> None:
    _require_exact_keys(payload, {"plan_description", "execution_config", "reason"}, "update_plan payload")
    _require_object(payload["plan_description"], "plan_description")
    _require_object(payload["execution_config"], "execution_config")
    _require_non_empty_string(payload["reason"], "reason")


def _validate_dispatch(payload: Mapping[str, Any]) -> None:
    _require_exact_keys(payload, {"target_agent_name", "input_source"}, "dispatch payload")
    _require_non_empty_string(payload["target_agent_name"], "target_agent_name")
    input_source = payload["input_source"]
    _require_object(input_source, "input_source")
    _require_exact_keys(input_source, {"type", "data"}, "input_source")
    if input_source["type"] not in {"variable", "tool"}:
        _invalid("input_source.type must be 'variable' or 'tool'")
    _require_object(input_source["data"], "input_source.data")
    if input_source["type"] == "tool":
        _require_exact_keys(input_source["data"], {"tool_name", "arguments"}, "input_source.data")
        _require_non_empty_string(input_source["data"]["tool_name"], "tool_name")
        _require_object(input_source["data"]["arguments"], "arguments")


def _validate_accept_output(payload: Mapping[str, Any]) -> None:
    _require_exact_keys(payload, {"decision", "reason"}, "accept_output payload")
    if payload["decision"] not in {"Accept", "Reject"}:
        _invalid("decision must be 'Accept' or 'Reject'")
    _require_non_empty_string(payload["reason"], "reason")


def _validate_finish(payload: Mapping[str, Any]) -> None:
    _require_exact_keys(payload, {"final_result", "summary"}, "finish payload")
    _require_object(payload["final_result"], "final_result")
    _require_non_empty_string(payload["summary"], "summary")


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value.keys())
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing keys: {', '.join(missing)}")
        if extra:
            parts.append(f"extra keys: {', '.join(extra)}")
        _invalid(f"{label} has invalid keys ({'; '.join(parts)})")


def _require_uuid(value: Any, label: str) -> None:
    if not isinstance(value, str):
        _invalid(f"{label} must be a string UUID")
    try:
        UUID(value)
    except ValueError:
        _invalid(f"{label} must be a valid UUID")


def _require_non_empty_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        _invalid(f"{label} must be a non-empty string")


def _require_object(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        _invalid(f"{label} must be an object")


def _invalid(message: str) -> None:
    raise AutoHarnessError(ErrorCode.SCHEMA_INVALID, message)
