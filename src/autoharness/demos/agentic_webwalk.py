"""Agentic WebWalk loop where a model emits tool actions."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Protocol

from autoharness.demos.io import emit_result
from autoharness.llm import ChatClient, ChatConfig
from autoharness.schema_validation import require_valid_with_schema
from autoharness.webwalk import WebPage, WebWalkLimits, WebWalkTool, page_observation


RESULT_SCHEMA = "schemas/tasks/atcoder_problem_editorial.schema.json"
PLANNER_ACTION_SCHEMA = "schemas/tools/webwalk-planner-action.schema.json"


class JsonPlanner(Protocol):
    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Return the next orchestrator action as a JSON object."""


@dataclass(frozen=True)
class AgenticRunConfig:
    contest_id: str
    problem_id: str
    max_steps: int = 8
    use_schema_validation: bool = False

    @property
    def problem_url(self) -> str:
        return f"https://atcoder.jp/contests/{self.contest_id}/tasks/{self.problem_id}"

    @property
    def editorial_index_url(self) -> str:
        return f"https://atcoder.jp/contests/{self.contest_id}/editorial"


class MiniMaxPlanner:
    def __init__(self) -> None:
        self.client = ChatClient(ChatConfig.from_env())

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return self.client.complete_json(messages)


class ScriptedPlanner:
    """Deterministic planner for tests."""

    def __init__(self, actions: list[dict[str, Any]]) -> None:
        self.actions = list(actions)

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if not self.actions:
            raise AssertionError("scripted planner exhausted")
        return self.actions.pop(0)


def run_agentic_webwalk(
    config: AgenticRunConfig,
    *,
    planner: JsonPlanner,
    walker: WebWalkTool | None = None,
) -> dict[str, Any]:
    walker = walker or WebWalkTool(
        allowed_domains=["atcoder.jp"],
        limits=WebWalkLimits(max_pages=config.max_steps, request_delay_ms=1000, timeout_seconds=30),
    )
    messages = [
        {
            "role": "system",
            "content": system_prompt(),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "Find the specific AtCoder problem editorial. You must navigate with actions.",
                    "contest_id": config.contest_id,
                    "problem_id": config.problem_id,
                    "allowed_start_urls": [config.problem_url, config.editorial_index_url],
                    "final_schema_summary": {
                        "contest_id": "string",
                        "problem_id": "string",
                        "problem_title": "string",
                        "problem_url": "string",
                        "editorial_index_url": "string",
                        "editorial_url": "string",
                        "editorial_title": "string",
                        "editorial_text_excerpt": "string",
                        "evidence": [{"url": "string", "reason": "string"}],
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]

    action_log: list[dict[str, Any]] = []
    for step in range(1, config.max_steps + 1):
        action = planner.complete_json(messages)
        validate_planner_action(action)
        action_log.append({"step": step, "action": action})
        action_type = action.get("action")

        if action_type == "open_url":
            page = walker.open(_require_string(action, "url"))
            observation = observation_for_page(page)
        elif action_type == "open_link":
            page = walker.open_link(_require_int(action, "link_id"))
            observation = observation_for_page(page)
        elif action_type == "final":
            result = _require_object(action, "result")
            result = normalize_final_result(result, config=config, walker=walker, action_log=action_log)
            if config.use_schema_validation:
                require_valid_with_schema(result, RESULT_SCHEMA)
            return result
        else:
            observation = {
                "error": f"unsupported action: {action_type!r}",
                "allowed_actions": ["open_url", "open_link", "final"],
            }

        messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        messages.append({"role": "user", "content": json.dumps({"observation": observation}, ensure_ascii=False)})

    raise RuntimeError(f"agentic webwalk did not finish within {config.max_steps} steps")


def system_prompt() -> str:
    return (
        "You are the AutoHarness Orchestrator for a restricted WebWalk task. "
        "Return exactly one JSON object per turn. No markdown. No prose. "
        "Allowed actions: "
        '{"action":"open_url","url":"https://atcoder.jp/..."}; '
        '{"action":"open_link","link_id":0}; '
        '{"action":"final","result":{...}}. '
        "Use only atcoder.jp URLs. First inspect the problem page, then the editorial index, "
        "then open the specific editorial page. The final result must include evidence as an "
        "array of objects shaped like {\"url\":\"https://...\",\"reason\":\"...\"}, not strings. "
        "Do not invent webwalk_trace; the Runtime will attach the executed trace."
    )


def observation_for_page(page: WebPage) -> dict[str, Any]:
    return page_observation(page)


def validate_planner_action(action: dict[str, Any]) -> None:
    require_valid_with_schema(action, PLANNER_ACTION_SCHEMA)


def normalize_final_result(
    result: dict[str, Any],
    *,
    config: AgenticRunConfig,
    walker: WebWalkTool,
    action_log: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized = dict(result)
    pages = _pages_from_walker(walker)
    problem_page = _find_page(pages, config.problem_url)
    current_page = _current_page(walker, pages)
    editorial_index_page = _find_editorial_index_page(pages, config=config, editorial_page=current_page)

    normalized.setdefault("contest_id", config.contest_id)
    normalized.setdefault("problem_id", config.problem_id)
    normalized.setdefault("problem_url", config.problem_url)
    normalized.setdefault("editorial_index_url", config.editorial_index_url)
    if problem_page is not None:
        normalized["problem_url"] = problem_page.url
        normalized["problem_title"] = _title_without_atcoder(problem_page.title) or config.problem_id
    if editorial_index_page is not None:
        normalized["editorial_index_url"] = editorial_index_page.url
    if current_page is not None:
        normalized["editorial_url"] = current_page.url
        normalized["editorial_title"] = current_page.title or normalized.get("editorial_title") or "Editorial"
        normalized["editorial_text_excerpt"] = current_page.text[:4000]

    if not _non_empty_string(normalized.get("problem_title")):
        normalized["problem_title"] = _title_without_atcoder(problem_page.title) if problem_page else config.problem_id
    if not _non_empty_string(normalized.get("editorial_url")) and current_page is not None:
        normalized["editorial_url"] = current_page.url
    if not _non_empty_string(normalized.get("editorial_title")) and current_page is not None:
        normalized["editorial_title"] = current_page.title or "Editorial"
    if not _non_empty_string(normalized.get("editorial_text_excerpt")) and current_page is not None:
        normalized["editorial_text_excerpt"] = current_page.text[:4000]

    normalized["evidence"] = _normalize_evidence(
        normalized.get("evidence"),
        problem_page=problem_page,
        editorial_index_page=editorial_index_page,
        editorial_page=current_page,
        visited_urls={page.url for page in pages},
    )
    normalized["webwalk_trace"] = walker.trace()
    normalized["agentic_action_trace"] = action_log
    return normalized


def _normalize_evidence(
    evidence: Any,
    *,
    problem_page: WebPage | None,
    editorial_index_page: WebPage | None,
    editorial_page: WebPage | None,
    visited_urls: set[str],
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, str):
                if item in visited_urls:
                    _append_evidence(normalized, seen, item, "Model cited this visited URL.")
            elif isinstance(item, dict):
                url = item.get("url")
                reason = item.get("reason")
                if isinstance(url, str) and url in visited_urls and isinstance(reason, str) and reason.strip():
                    _append_evidence(normalized, seen, url, reason)

    if problem_page is not None:
        _append_evidence(
            normalized,
            seen,
            problem_page.url,
            "Problem page confirms the requested problem.",
        )
    if editorial_index_page is not None:
        _append_evidence(
            normalized,
            seen,
            editorial_index_page.url,
            "Contest editorial index was inspected for candidate editorial links.",
        )
    if editorial_page is not None:
        _append_evidence(
            normalized,
            seen,
            editorial_page.url,
            "Selected editorial detail page was opened through WebWalk.",
        )
    return normalized


def _append_evidence(items: list[dict[str, str]], seen: set[str], url: str, reason: str) -> None:
    if not url.startswith(("http://", "https://")) or url in seen:
        return
    seen.add(url)
    items.append({"url": url, "reason": reason.strip()})


def _pages_from_walker(walker: WebWalkTool) -> list[WebPage]:
    pages = getattr(walker, "pages", [])
    return list(pages) if isinstance(pages, list) else []


def _find_page(pages: list[WebPage], url: str) -> WebPage | None:
    for page in pages:
        if page.url == url:
            return page
    return None


def _find_editorial_index_page(
    pages: list[WebPage],
    *,
    config: AgenticRunConfig,
    editorial_page: WebPage | None,
) -> WebPage | None:
    exact = _find_page(pages, config.editorial_index_url)
    if exact is not None:
        return exact
    editorial_url = editorial_page.url if editorial_page is not None else None
    for page in pages:
        if page.url == editorial_url:
            continue
        if page.url.endswith("/editorial"):
            return page
    return None


def _current_page(walker: WebWalkTool, pages: list[WebPage]) -> WebPage | None:
    current_page = getattr(walker, "current_page", None)
    if callable(current_page):
        return current_page()
    if pages:
        return pages[-1]
    return None


def _title_without_atcoder(title: str) -> str:
    return title.split(" - AtCoder", 1)[0] if " - AtCoder" in title else title


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_string(action: dict[str, Any], key: str) -> str:
    value = action.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"action.{key} must be a non-empty string")
    return value


def _require_int(action: dict[str, Any], key: str) -> int:
    value = action.get(key)
    if not isinstance(value, int):
        raise ValueError(f"action.{key} must be an integer")
    return value


def _require_object(action: dict[str, Any], key: str) -> dict[str, Any]:
    value = action.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"action.{key} must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an agentic AtCoder WebWalk demo.")
    parser.add_argument("contest_id", help="Contest id, for example abc220.")
    parser.add_argument("problem_id", help="Problem id, for example abc220_a.")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--output", help="Optional path to write the JSON result.")
    parser.add_argument("--validate-schema", action="store_true", help="Validate output against the task schema.")
    args = parser.parse_args(argv)

    result = run_agentic_webwalk(
        AgenticRunConfig(
            contest_id=args.contest_id,
            problem_id=args.problem_id,
            max_steps=args.max_steps,
            use_schema_validation=args.validate_schema,
        ),
        planner=MiniMaxPlanner(),
    )
    emit_result(result, output=args.output, schema_path=RESULT_SCHEMA if args.validate_schema else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
