"""HarnessSpec compilation and execution primitives."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from autoharness.runtime import AgentExecutor, Runtime
from autoharness.schema_validation import require_valid_with_schema
from autoharness.tool_host import ToolHandler, ToolHost


HARNESS_SPEC_SCHEMA = "schemas/harness-spec.schema.json"


class HarnessBuilder(Protocol):
    def build(self, task: Mapping[str, Any]) -> dict[str, Any]:
        """Build a HarnessSpec from a task description."""


@dataclass(frozen=True)
class HarnessRunResult:
    harness_id: str
    trace_id: str
    actions: list[dict[str, Any]]
    snapshot: dict[str, Any]


def require_valid_harness_spec(spec: Mapping[str, Any]) -> None:
    require_valid_with_schema(dict(spec), HARNESS_SPEC_SCHEMA)


def run_harness_spec(
    spec: Mapping[str, Any],
    *,
    executor: AgentExecutor,
    tools: Mapping[str, ToolHandler] | ToolHost | None = None,
    trace_id: str | None = None,
) -> HarnessRunResult:
    require_valid_harness_spec(spec)
    run_trace_id = trace_id or str(uuid5(NAMESPACE_URL, f"autoharness:run:{spec['harness_id']}"))
    runtime = Runtime(executor=executor, tools=tools)
    actions: list[dict[str, Any]] = []

    def apply(action: dict[str, Any]) -> None:
        runtime.apply(action)
        actions.append(deepcopy(action))

    apply(_action(spec, run_trace_id, "update_plan", "update-plan", _plan_payload(spec)))
    for agent in spec["agents"]:
        apply(_action(spec, run_trace_id, "create_agent", f"create-agent:{agent['name']}", deepcopy(agent)))

    for step in spec["workflow"]:
        step_type = step["type"]
        if step_type == "dispatch":
            input_source = _resolve_input_source(step["input_source"], runtime.current_payload)
            apply(
                _action(
                    spec,
                    run_trace_id,
                    "dispatch",
                    step["step_id"],
                    {
                        "target_agent_name": step["target_agent_name"],
                        "input_source": input_source,
                    },
                )
            )
        elif step_type == "accept_output":
            apply(
                _action(
                    spec,
                    run_trace_id,
                    "accept_output",
                    step["step_id"],
                    {
                        "decision": step["decision"],
                        "reason": step["reason"],
                    },
                )
            )
        elif step_type == "finish":
            apply(
                _action(
                    spec,
                    run_trace_id,
                    "finish",
                    step["step_id"],
                    {
                        "final_result": deepcopy(runtime.current_payload),
                        "summary": step["summary"],
                    },
                )
            )
        else:
            raise ValueError(f"unsupported harness workflow step type: {step_type}")

    return HarnessRunResult(
        harness_id=str(spec["harness_id"]),
        trace_id=run_trace_id,
        actions=actions,
        snapshot=runtime.snapshot(),
    )


def _plan_payload(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "plan_description": {
            "harness_id": spec["harness_id"],
            "name": spec["name"],
            "task": deepcopy(spec["task"]),
            "acceptance": deepcopy(spec["acceptance"]),
        },
        "execution_config": {
            "tools": [tool["name"] for tool in spec["tools"]],
            "workflow_steps": len(spec["workflow"]),
        },
        "reason": "Initialize harness execution plan.",
    }


def _action(
    spec: Mapping[str, Any],
    trace_id: str,
    action_type: str,
    key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "action_id": str(uuid5(NAMESPACE_URL, f"autoharness:{spec['harness_id']}:{trace_id}:{key}")),
        "trace_id": _uuid_string(trace_id),
        "action_type": action_type,
        "payload": payload,
    }


def _resolve_input_source(input_source: Mapping[str, Any], current_payload: Mapping[str, Any]) -> dict[str, Any]:
    return _resolve_value(input_source, current_payload)


def _resolve_value(value: Any, current_payload: Mapping[str, Any]) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$from_current_payload"}:
            return _lookup_path(current_payload, value["$from_current_payload"])
        return {key: _resolve_value(item, current_payload) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, current_payload) for item in value]
    return deepcopy(value)


def _lookup_path(payload: Mapping[str, Any], path: Any) -> Any:
    if not isinstance(path, str) or not path:
        raise ValueError("$from_current_payload must be a non-empty dotted path")
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise ValueError(f"current_payload path not found: {path}")
        value = value[part]
    return deepcopy(value)


def _uuid_string(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, value))
