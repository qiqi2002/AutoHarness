"""Command line runner for HarnessSpec files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from autoharness.harness import HarnessRunResult, run_harness_spec
from autoharness.harness_executors import AtCoderLatestEditorialExecutor, AtCoderProblemEditorialExecutor
from autoharness.llm import ChatClient, ChatConfig
from autoharness.model_harness import ModelAgentExecutor
from autoharness.runtime import AgentExecutor
from autoharness.schema_validation import load_json, require_valid_with_schema
from autoharness.webwalk import WebWalkLimits, WebWalkRuntimeTool, WebWalkTool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an AutoHarness HarnessSpec.")
    parser.add_argument("harness", help="Path to a HarnessSpec JSON file.")
    parser.add_argument(
        "--executor",
        choices=["auto", "atcoder_problem_editorial", "atcoder_latest_editorial", "model"],
        default="auto",
        help="AgentExecutor to use. auto selects a task-aware executor from spec.task.name.",
    )
    parser.add_argument("--output", help="Optional path to write the final_result JSON.")
    parser.add_argument("--trace-output", help="Optional path to write actions and runtime snapshot JSON.")
    parser.add_argument(
        "--skip-acceptance-validation",
        action="store_true",
        help="Run without validating the final_result against HarnessSpec acceptance rules.",
    )
    args = parser.parse_args(argv)

    spec = _load_json(Path(args.harness))
    result = run_harness_spec(
        spec,
        executor=_build_executor(spec, args.executor),
        tools=_build_tools(spec),
    )
    final_result = _require_final_result(result)
    if not args.skip_acceptance_validation:
        validate_acceptance(final_result, spec)

    _emit_json(final_result, output=args.output)
    if args.trace_output:
        _write_json(
            {
                "harness_id": result.harness_id,
                "trace_id": result.trace_id,
                "actions": result.actions,
                "snapshot": result.snapshot,
            },
            Path(args.trace_output),
        )
    return 0


def validate_acceptance(final_result: Mapping[str, Any], spec: Mapping[str, Any]) -> None:
    for rule in spec.get("acceptance", {}).get("rules", []):
        rule_type = rule.get("type")
        if rule_type == "schema":
            schema_path = rule.get("schema")
            if not isinstance(schema_path, str):
                raise ValueError("schema acceptance rule requires a string schema path")
            require_valid_with_schema(dict(final_result), schema_path)
        elif rule_type == "evidence_urls_must_be_visited":
            _require_evidence_urls_visited(final_result)
        else:
            raise ValueError(f"unsupported acceptance rule type: {rule_type}")


def _build_executor(spec: Mapping[str, Any], executor_name: str) -> AgentExecutor:
    selected = spec.get("task", {}).get("name") if executor_name == "auto" else executor_name
    if selected == "atcoder_problem_editorial":
        inputs = spec.get("task", {}).get("inputs", {})
        return AtCoderProblemEditorialExecutor(
            contest_id=_optional_string(inputs.get("contest_id")),
            problem_id=_optional_string(inputs.get("problem_id")),
        )
    if selected == "atcoder_latest_editorial":
        return AtCoderLatestEditorialExecutor()
    if selected == "model":
        return ModelAgentExecutor(ChatClient(ChatConfig.from_env()), output_schema=_task_output_schema(spec))
    raise ValueError(f"no executor is available for task/executor: {selected}")


def _build_tools(spec: Mapping[str, Any]) -> dict[str, WebWalkRuntimeTool]:
    tools: dict[str, WebWalkRuntimeTool] = {}
    for tool in spec.get("tools", []):
        if tool.get("kind") != "runtime_tool":
            raise ValueError(f"unsupported tool kind: {tool.get('kind')}")
        name = tool.get("name")
        if name != "webwalk":
            raise ValueError(f"unsupported runtime tool: {name}")
        config = tool.get("config", {})
        if not isinstance(config, Mapping):
            raise ValueError("webwalk tool config must be an object")
        limits_config = config.get("limits", {})
        if not isinstance(limits_config, Mapping):
            raise ValueError("webwalk limits config must be an object")
        walker = WebWalkTool(
            allowed_domains=_required_string_list(config.get("allowed_domains"), "webwalk.allowed_domains"),
            limits=WebWalkLimits(
                max_pages=int(limits_config.get("max_pages", 12)),
                max_depth=int(limits_config.get("max_depth", 5)),
                timeout_seconds=int(limits_config.get("timeout_seconds", 30)),
                request_delay_ms=int(limits_config.get("request_delay_ms", 1000)),
                max_text_chars=int(limits_config.get("max_text_chars", 12000)),
            ),
        )
        tools[name] = WebWalkRuntimeTool(walker)
    return tools


def _require_final_result(result: HarnessRunResult) -> dict[str, Any]:
    final_result = result.snapshot.get("final_result")
    if not isinstance(final_result, dict):
        raise ValueError("harness did not produce a final_result object")
    return final_result


def _task_output_schema(spec: Mapping[str, Any]) -> dict[str, Any] | None:
    ref = spec.get("task", {}).get("output_schema", {}).get("$ref")
    if not isinstance(ref, str):
        return None
    schema = load_json(ref)
    if not isinstance(schema, dict):
        raise ValueError(f"task output schema must be an object: {ref}")
    return schema


def _require_evidence_urls_visited(final_result: Mapping[str, Any]) -> None:
    visited = {
        step.get("url")
        for step in final_result.get("webwalk_trace", [])
        if isinstance(step, Mapping) and isinstance(step.get("url"), str)
    }
    missing = [
        evidence.get("url")
        for evidence in final_result.get("evidence", [])
        if isinstance(evidence, Mapping) and evidence.get("url") not in visited
    ]
    if missing:
        raise ValueError(f"evidence URLs were not visited: {', '.join(str(url) for url in missing)}")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit_json(data: Mapping[str, Any], *, output: str | None) -> None:
    if output:
        _write_json(data, Path(output))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _write_json(data: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _required_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} must be a non-empty list of strings")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
