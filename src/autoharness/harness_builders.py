"""Deterministic HarnessSpec builders used as local baselines."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from autoharness.schema_validation import load_json


class AtCoderProblemEditorialHarnessBuilder:
    """Build a WebWalk harness for a known AtCoder problem editorial task.

    This builder is intentionally deterministic. It represents the shape a
    strong Orchestrator should produce, while keeping tests independent from a
    live model call.
    """

    def build(self, task: Mapping[str, Any]) -> dict[str, Any]:
        inputs = dict(task["inputs"])
        contest_id = inputs["contest_id"]
        problem_id = inputs["problem_id"]
        problem_url = _format_url(task, "problem", inputs)
        editorial_index_url = _format_url(task, "editorial_index", inputs)
        editorial_url = inputs.get("editorial_url") or f"https://atcoder.jp/contests/{contest_id}/editorial"

        return {
            "schema_version": "1.0",
            "harness_id": f"atcoder-problem-editorial-{contest_id}-{problem_id}",
            "name": "atcoder_problem_editorial_harness",
            "description": "Weak-model harness for extracting one AtCoder problem editorial through Runtime WebWalk.",
            "task": {
                "name": task["name"],
                "inputs": {
                    **inputs,
                    "problem_url": problem_url,
                    "editorial_index_url": editorial_index_url,
                    "editorial_url": editorial_url,
                },
                "output_schema": _output_schema(task),
            },
            "agents": [
                {
                    "name": "atcoder_extractor",
                    "role": "Weak model that accumulates visited AtCoder pages and extracts the final editorial result.",
                    "prompt": (
                        "Use only Runtime-provided WebWalk observations. Preserve evidence URLs from the trace. "
                        "Return an object matching the task output schema when enough pages have been observed."
                    ),
                    "io_schema": {
                        "type": "object",
                    },
                }
            ],
            "tools": [
                {
                    "name": "webwalk",
                    "kind": "runtime_tool",
                    "config": {
                        "allowed_domains": deepcopy(task.get("allowed_domains", ["atcoder.jp"])),
                        "limits": deepcopy(task.get("limits", {})),
                    },
                }
            ],
            "workflow": [
                _dispatch_step("open-problem", problem_url),
                _accept_step("accept-problem", "Accept the problem-page observation."),
                _dispatch_step("open-editorial-index", editorial_index_url),
                _accept_step("accept-editorial-index", "Accept the editorial-index observation."),
                _dispatch_step("open-editorial-page", editorial_url),
                _accept_step("accept-editorial-page", "Accept the selected editorial-page observation."),
                {
                    "step_id": "finish",
                    "type": "finish",
                    "summary": "Completed the generated AtCoder problem editorial harness.",
                },
            ],
            "acceptance": {
                "rules": [
                    {
                        "type": "schema",
                        "schema": "schemas/tasks/atcoder_problem_editorial.schema.json",
                    },
                    {
                        "type": "evidence_urls_must_be_visited",
                    },
                ]
            },
            "evaluations": [
                {
                    "type": "recorded_fixture",
                    "path": "examples/recorded/atcoder_problem_editorial_abc220_a.json",
                }
            ],
        }


def _format_url(task: Mapping[str, Any], template_name: str, inputs: Mapping[str, Any]) -> str:
    return task["url_templates"][template_name].format(**inputs)


def _output_schema(task: Mapping[str, Any]) -> dict[str, Any]:
    schema = task.get("output_schema")
    if isinstance(schema, dict):
        return deepcopy(schema)
    if isinstance(schema, str) and Path(schema).exists():
        return load_json(schema)
    return {"$ref": str(schema)}


def _dispatch_step(step_id: str, url: str) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "type": "dispatch",
        "target_agent_name": "atcoder_extractor",
        "input_source": {
            "type": "tool",
            "data": {
                "tool_name": "webwalk",
                "arguments": {
                    "operation": "open_url",
                    "url": url,
                },
            },
        },
    }


def _accept_step(step_id: str, reason: str) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "type": "accept_output",
        "decision": "Accept",
        "reason": reason,
    }
