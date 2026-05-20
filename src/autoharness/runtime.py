"""M1 Runtime state machine and double-buffer commit semantics."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from autoharness.actions import Action, validate_action
from autoharness.errors import AutoHarnessError, ErrorCode


class RuntimeState(str, Enum):
    INIT = "INIT"
    PLANNING = "PLANNING"
    BUILDING_AGENTS = "BUILDING_AGENTS"
    EXECUTING = "EXECUTING"
    AWAITING_ACCEPTANCE = "AWAITING_ACCEPTANCE"
    REPLANNING = "REPLANNING"
    FINALIZING = "FINALIZING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    role: str
    prompt: str
    io_schema: dict[str, Any]


class AgentExecutor(Protocol):
    def dispatch(
        self,
        agent: AgentDefinition,
        input_source: Mapping[str, Any],
        current_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return a candidate output for `temp_buffer`."""


class StaticAgentExecutor:
    """Deterministic test executor keyed by agent name."""

    def __init__(self, outputs: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.outputs = {name: dict(output) for name, output in (outputs or {}).items()}

    def dispatch(
        self,
        agent: AgentDefinition,
        input_source: Mapping[str, Any],
        current_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if agent.name in self.outputs:
            return deepcopy(self.outputs[agent.name])
        return {
            "agent": agent.name,
            "input_source": deepcopy(dict(input_source)),
            "current_payload": deepcopy(dict(current_payload)),
        }


class Runtime:
    """Runtime implementation for the M1 Action contract."""

    def __init__(
        self,
        *,
        executor: AgentExecutor | None = None,
        tools: Mapping[str, Any] | None = None,
        initial_payload: Mapping[str, Any] | None = None,
    ) -> None:
        self.state = RuntimeState.PLANNING
        self.state_version = 1
        self.current_payload: dict[str, Any] = dict(initial_payload or {})
        self.temp_buffer: dict[str, Any] | None = None
        self.plan_description: dict[str, Any] | None = None
        self.execution_config: dict[str, Any] | None = None
        self.agents: dict[str, AgentDefinition] = {}
        self.completed_action_ids: set[str] = set()
        self.trace: list[Action] = []
        self.final_result: dict[str, Any] | None = None
        self.summary: str | None = None
        self.executor = executor or StaticAgentExecutor()
        self.tools = dict(tools or {})

    def apply(self, raw_action: Mapping[str, Any]) -> None:
        action = validate_action(raw_action)
        self._guard_idempotency(action)
        self._guard_temp_buffer(action)
        self._guard_state(action)

        handlers = {
            "update_plan": self._apply_update_plan,
            "create_agent": self._apply_create_agent,
            "update_agent": self._apply_update_agent,
            "dispatch": self._apply_dispatch,
            "accept_output": self._apply_accept_output,
            "finish": self._apply_finish,
        }
        handlers[action.action_type](action)

        self.completed_action_ids.add(action.action_id)
        self.trace.append(action)
        self.state_version += 1

    def run_trace(self, actions: list[Mapping[str, Any]]) -> None:
        for action in actions:
            self.apply(action)

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "state_version": self.state_version,
            "current_payload": deepcopy(self.current_payload),
            "temp_buffer": deepcopy(self.temp_buffer),
            "agents": sorted(self.agents.keys()),
            "final_result": deepcopy(self.final_result),
            "summary": self.summary,
        }

    def _guard_idempotency(self, action: Action) -> None:
        if action.action_id in self.completed_action_ids:
            raise AutoHarnessError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                f"action_id already executed: {action.action_id}",
            )

    def _guard_temp_buffer(self, action: Action) -> None:
        if self.temp_buffer is not None and action.action_type != "accept_output":
            raise AutoHarnessError(
                ErrorCode.TEMP_BUFFER_LOCKED,
                "temp_buffer is awaiting acceptance",
            )

    def _guard_state(self, action: Action) -> None:
        allowed = {
            RuntimeState.PLANNING: {"update_plan"},
            RuntimeState.BUILDING_AGENTS: {"create_agent", "update_agent", "dispatch"},
            RuntimeState.EXECUTING: {"dispatch", "finish"},
            RuntimeState.AWAITING_ACCEPTANCE: {"accept_output"},
            RuntimeState.REPLANNING: {"update_plan", "update_agent"},
            RuntimeState.FINALIZING: set(),
            RuntimeState.DONE: set(),
            RuntimeState.FAILED: set(),
            RuntimeState.INIT: set(),
        }
        if action.action_type not in allowed[self.state]:
            raise AutoHarnessError(
                ErrorCode.ACTION_NOT_ALLOWED,
                f"{action.action_type} is not allowed in {self.state}",
            )

    def _apply_update_plan(self, action: Action) -> None:
        self.plan_description = deepcopy(action.payload["plan_description"])
        self.execution_config = deepcopy(action.payload["execution_config"])
        if self.state == RuntimeState.PLANNING:
            self.state = RuntimeState.BUILDING_AGENTS
        elif self.state == RuntimeState.REPLANNING:
            self.state = RuntimeState.EXECUTING

    def _apply_create_agent(self, action: Action) -> None:
        payload = action.payload
        self.agents[payload["name"]] = AgentDefinition(
            name=payload["name"],
            role=payload["role"],
            prompt=payload["prompt"],
            io_schema=deepcopy(payload["io_schema"]),
        )

    def _apply_update_agent(self, action: Action) -> None:
        payload = action.payload
        name = payload["name"]
        if name not in self.agents:
            raise AutoHarnessError(ErrorCode.AGENT_NOT_FOUND, f"agent not found: {name}")
        agent = self.agents[name]
        self.agents[name] = AgentDefinition(
            name=agent.name,
            role=agent.role,
            prompt=payload["new_prompt"],
            io_schema=deepcopy(agent.io_schema),
        )
        if self.state == RuntimeState.REPLANNING:
            self.state = RuntimeState.EXECUTING

    def _apply_dispatch(self, action: Action) -> None:
        payload = action.payload
        agent_name = payload["target_agent_name"]
        if agent_name not in self.agents:
            raise AutoHarnessError(ErrorCode.AGENT_NOT_FOUND, f"agent not found: {agent_name}")

        input_source = payload["input_source"]
        if input_source["type"] == "tool":
            tool_name = input_source["data"].get("tool_name")
            if not isinstance(tool_name, str) or tool_name not in self.tools:
                raise AutoHarnessError(ErrorCode.TOOL_NOT_FOUND, f"tool not found: {tool_name}")

        self.temp_buffer = self.executor.dispatch(
            self.agents[agent_name],
            deepcopy(input_source),
            deepcopy(self.current_payload),
        )
        if not isinstance(self.temp_buffer, dict):
            raise AutoHarnessError(
                ErrorCode.SCHEMA_INVALID,
                "agent executor output must be an object",
            )
        self.state = RuntimeState.AWAITING_ACCEPTANCE

    def _apply_accept_output(self, action: Action) -> None:
        decision = action.payload["decision"]
        if decision == "Accept":
            self.current_payload = deepcopy(self.temp_buffer or {})
            self.temp_buffer = None
            self.state = RuntimeState.EXECUTING
        else:
            self.temp_buffer = None
            self.state = RuntimeState.REPLANNING

    def _apply_finish(self, action: Action) -> None:
        self.final_result = deepcopy(action.payload["final_result"])
        self.summary = action.payload["summary"]
        self.state = RuntimeState.FINALIZING
        self.state = RuntimeState.DONE
