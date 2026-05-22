"""Model-backed harness builders and weak-model executors."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Mapping

from autoharness.harness import require_valid_harness_spec
from autoharness.llm import ChatClient, extract_json_object, strip_think_blocks
from autoharness.runtime import AgentDefinition


class ModelHarnessBuilder:
    """Ask a strong model to generate a HarnessSpec."""

    def __init__(self, client: ChatClient, *, max_retries: int = 2) -> None:
        self.client = client
        self.max_retries = max_retries

    def build(self, task: Mapping[str, Any]) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the strong AutoHarness Orchestrator. Generate exactly one HarnessSpec JSON object. "
                    "Do not include markdown. The schema is strict: do not add extra properties. "
                    "Top-level keys must be schema_version, harness_id, name, description, task, agents, tools, workflow, acceptance, optional plan, and optional evaluations. "
                    "When useful, include a plan before workflow. Plan is an auditable intent graph, not executable code. "
                    "Plan must have representation, summary, assumptions, nodes, edges, success_criteria, and divergence_policy. "
                    "Each plan node must have id, kind, label, description, expected_evidence, and workflow_step_ids that point to workflow step_id values. "
                    "Plan node kind must be one of observe, decide, extract, verify, finish. "
                    "Plan divergence_policy.detect_with must be an array of strings. "
                    "Plan divergence_policy.on_divergence must be exactly one of revise_plan, reject_output, fail_run. "
                    "The HarnessSpec task object must have exactly name, inputs, and output_schema; do not copy extra source task keys into task. "
                    "If the source task has output_schema as a string path, represent it as {'$ref':'that/path.json'}. "
                    "Each agent must have exactly name, role, prompt, io_schema. "
                    "Each tool must have exactly name, kind, config. Use kind='runtime_tool' for webwalk. "
                    "Acceptance must be {'rules':[objects...]}; never use plain strings as acceptance rules. "
                    "For schema acceptance use {'type':'schema','schema':'path/to/schema.json'}. "
                    "Workflow supports only these step shapes: "
                    "dispatch={step_id,type:'dispatch',target_agent_name,input_source}; "
                    "accept={step_id,type:'accept_output',decision:'Accept'|'Reject',reason}; "
                    "finish={step_id,type:'finish',summary}. "
                    "Tool input_source must be {type:'tool',data:{tool_name,arguments}}. "
                    "Use {'$from_current_payload':'field_name'} for dynamic values accepted from prior steps."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "minimal_dispatch_step_example": {
                            "step_id": "open-page",
                            "type": "dispatch",
                            "target_agent_name": "extractor",
                            "input_source": {
                                "type": "tool",
                                "data": {
                                    "tool_name": "webwalk",
                                    "arguments": {
                                        "operation": "open_url",
                                        "url": "https://atcoder.jp/",
                                    },
                                },
                            },
                        },
                        "minimal_accept_step_example": {
                            "step_id": "accept-page",
                            "type": "accept_output",
                            "decision": "Accept",
                            "reason": "Accept the candidate payload.",
                        },
                        "minimal_finish_step_example": {
                            "step_id": "finish",
                            "type": "finish",
                            "summary": "Completed the harness.",
                        },
                        "minimal_task_example": {
                            "name": "task_name",
                            "inputs": {"source_url": "https://example.com/"},
                            "output_schema": {"$ref": "schemas/tasks/task_name.schema.json"},
                        },
                        "minimal_acceptance_example": {
                            "rules": [
                                {"type": "schema", "schema": "schemas/tasks/task_name.schema.json"},
                                {"type": "evidence_urls_must_be_visited"},
                            ]
                        },
                        "minimal_plan_example": {
                            "representation": "sequence",
                            "summary": "Observe source page, extract task result, verify evidence, then finish.",
                            "assumptions": ["The source page is reachable by an allowed Runtime tool."],
                            "nodes": [
                                {
                                    "id": "observe-source",
                                    "kind": "observe",
                                    "label": "Observe source",
                                    "description": "Open the source page and capture evidence.",
                                    "expected_evidence": ["source page URL"],
                                    "workflow_step_ids": ["open-page", "accept-page"],
                                },
                                {
                                    "id": "finish",
                                    "kind": "finish",
                                    "label": "Finish",
                                    "description": "Finish after accepted payload satisfies the output schema.",
                                    "expected_evidence": [],
                                    "workflow_step_ids": ["finish"],
                                },
                            ],
                            "edges": [{"from": "observe-source", "to": "finish"}],
                            "success_criteria": [
                                "Final result matches the task output schema.",
                                "Evidence URLs were visited by Runtime.",
                            ],
                            "divergence_policy": {
                                "detect_with": ["schema validation", "evidence URL validation"],
                                "on_divergence": "reject_output",
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        last_error: Exception | None = None
        for _ in range(self.max_retries + 1):
            spec = self.client.complete_json(messages)
            try:
                require_valid_harness_spec(spec)
                return spec
            except ValueError as exc:
                last_error = exc
                messages.append({"role": "assistant", "content": json.dumps(spec, ensure_ascii=False)})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The HarnessSpec failed schema validation. Return a corrected full HarnessSpec JSON object only. "
                            f"Validation errors:\n{exc}"
                        ),
                    }
                )
        raise ValueError(f"model did not produce a valid HarnessSpec after retries: {last_error}")


class ModelAgentExecutor:
    """Use a weak model as Runtime AgentExecutor."""

    def __init__(
        self,
        client: ChatClient,
        *,
        output_schema: Mapping[str, Any] | None = None,
        max_retries: int = 1,
    ) -> None:
        self.client = client
        self.output_schema = deepcopy(dict(output_schema)) if output_schema else None
        self.max_retries = max_retries

    def dispatch(
        self,
        agent: AgentDefinition,
        input_source: Mapping[str, Any],
        current_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are weak model agent {agent.name}. Role: {agent.role}. "
                    f"Prompt: {agent.prompt} Return exactly one JSON object. No markdown. "
                    "Your output enters Runtime temp_buffer and replaces current_payload after acceptance. "
                    "Preserve relevant current_payload fields unless the new observation corrects them. "
                    "When the input is a tool result, preserve the Runtime-provided webwalk_trace and cite observed URLs in evidence. "
                    "Evidence URLs must be URLs that appear in webwalk_trace; do not cite linked pages as evidence unless Runtime opened them. "
                    "If a target_output_schema is provided and the current observation contains enough information, match that schema exactly."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "input_source": deepcopy(dict(input_source)),
                        "current_payload": deepcopy(dict(current_payload)),
                        "io_schema": agent.io_schema,
                        "target_output_schema": deepcopy(self.output_schema),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        last_error: Exception | None = None
        for _ in range(self.max_retries + 1):
            content = self.client.complete(messages)
            try:
                return extract_json_object(strip_think_blocks(content))
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was not parseable as one JSON object. "
                            "Return the corrected JSON object only, with no markdown or explanation. "
                            f"Parser error: {exc}"
                        ),
                    }
                )
        raise ValueError(f"model did not return valid JSON after retries: {last_error}")
