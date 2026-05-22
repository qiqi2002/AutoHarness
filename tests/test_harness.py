from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoharness.harness import require_valid_harness_spec, run_harness_spec
from autoharness.harness_builders import AtCoderLatestEditorialHarnessBuilder, AtCoderProblemEditorialHarnessBuilder
from autoharness.harness_executors import AtCoderLatestEditorialExecutor, AtCoderProblemEditorialExecutor
from autoharness.llm import ChatConfig
from autoharness.model_harness import ModelAgentExecutor, ModelHarnessBuilder
from autoharness.run_harness import validate_acceptance
from autoharness.webwalk import WebWalkRuntimeTool, parse_page


class HarnessSpecTest(unittest.TestCase):
    def test_static_atcoder_builder_produces_valid_harness_spec(self) -> None:
        task = json.loads((ROOT / "configs" / "tasks" / "atcoder_problem_editorial.json").read_text())
        task["inputs"]["editorial_url"] = "https://atcoder.jp/contests/abc220/editorial/2700"

        spec = AtCoderProblemEditorialHarnessBuilder().build(task)

        require_valid_harness_spec(spec)
        self.assertEqual(spec["harness_id"], "atcoder-problem-editorial-abc220-abc220_a")
        self.assertEqual(spec["plan"]["representation"], "sequence")
        self.assertEqual(spec["plan"]["nodes"][0]["workflow_step_ids"], ["open-problem", "accept-problem"])
        self.assertEqual(spec["workflow"][0]["type"], "dispatch")

    def test_generated_atcoder_harness_runs_through_runtime(self) -> None:
        spec = json.loads(
            (ROOT / "examples" / "harnesses" / "atcoder_problem_editorial_abc220_a.harness.json").read_text()
        )

        result = run_harness_spec(
            spec,
            executor=AtCoderFixtureExecutor(),
            tools={"webwalk": WebWalkRuntimeTool(AtCoderFixtureWalker())},
            trace_id="11111111-2222-4333-8444-555555555555",
        )

        self.assertEqual(result.snapshot["state"], "DONE")
        self.assertEqual(result.snapshot["current_payload"]["problem_id"], "abc220_a")
        self.assertEqual(result.snapshot["current_payload"]["editorial_url"], "https://atcoder.jp/contests/abc220/editorial/2700")
        self.assertEqual(len(result.snapshot["current_payload"]["webwalk_trace"]), 3)
        self.assertEqual([action["action_type"] for action in result.actions[:2]], ["update_plan", "create_agent"])

    def test_latest_editorial_builder_produces_valid_harness_spec(self) -> None:
        task = json.loads((ROOT / "configs" / "tasks" / "atcoder_latest_editorial.json").read_text())

        spec = AtCoderLatestEditorialHarnessBuilder().build(task)

        require_valid_harness_spec(spec)
        dynamic_url = spec["workflow"][2]["input_source"]["data"]["arguments"]["url"]
        self.assertEqual(dynamic_url, {"$from_current_payload": "editorial_url"})
        self.assertIn("latest finished contest", spec["plan"]["success_criteria"][2])

    def test_harness_run_records_plan_in_update_plan_action(self) -> None:
        spec = json.loads((ROOT / "examples" / "harnesses" / "atcoder_latest_editorial.harness.json").read_text())

        result = run_harness_spec(
            spec,
            executor=LatestEditorialFixtureExecutor(),
            tools={"webwalk": WebWalkRuntimeTool(LatestEditorialFixtureWalker())},
            trace_id="55555555-6666-4777-8888-999999999999",
        )

        plan = result.actions[0]["payload"]["plan_description"]["plan"]
        self.assertEqual(plan["nodes"][0]["id"], "observe-archive")
        self.assertEqual(plan["nodes"][0]["workflow_step_ids"], ["open-archive", "accept-archive"])

    def test_latest_editorial_harness_resolves_dynamic_tool_argument(self) -> None:
        spec = json.loads((ROOT / "examples" / "harnesses" / "atcoder_latest_editorial.harness.json").read_text())

        result = run_harness_spec(
            spec,
            executor=LatestEditorialFixtureExecutor(),
            tools={"webwalk": WebWalkRuntimeTool(LatestEditorialFixtureWalker())},
            trace_id="22222222-3333-4444-8555-666666666666",
        )

        self.assertEqual(result.snapshot["state"], "DONE")
        self.assertEqual(result.snapshot["current_payload"]["contest_id"], "abc999")
        self.assertEqual(result.snapshot["current_payload"]["editorial_url"], "https://atcoder.jp/contests/abc999/editorial")
        dispatch_actions = [action for action in result.actions if action["action_type"] == "dispatch"]
        self.assertEqual(
            dispatch_actions[1]["payload"]["input_source"]["data"]["arguments"]["url"],
            "https://atcoder.jp/contests/abc999/editorial",
        )

    def test_task_aware_problem_executor_produces_schema_valid_final_result(self) -> None:
        spec = json.loads(
            (ROOT / "examples" / "harnesses" / "atcoder_problem_editorial_abc220_a.harness.json").read_text()
        )

        result = run_harness_spec(
            spec,
            executor=AtCoderProblemEditorialExecutor(contest_id="abc220", problem_id="abc220_a"),
            tools={"webwalk": WebWalkRuntimeTool(AtCoderFixtureWalker())},
            trace_id="33333333-4444-4555-8666-777777777777",
        )

        final_result = result.snapshot["final_result"]
        validate_acceptance(final_result, spec)
        self.assertEqual(final_result["problem_id"], "abc220_a")
        self.assertEqual(final_result["editorial_url"], "https://atcoder.jp/contests/abc220/editorial/2700")

    def test_task_aware_latest_executor_produces_schema_valid_final_result(self) -> None:
        spec = json.loads((ROOT / "examples" / "harnesses" / "atcoder_latest_editorial.harness.json").read_text())

        result = run_harness_spec(
            spec,
            executor=AtCoderLatestEditorialExecutor(),
            tools={"webwalk": WebWalkRuntimeTool(LatestEditorialFixtureWalker())},
            trace_id="44444444-5555-4666-8777-888888888888",
        )

        final_result = result.snapshot["final_result"]
        validate_acceptance(final_result, spec)
        self.assertEqual(final_result["contest_id"], "abc999")
        self.assertEqual(final_result["problems"][0]["editorial_url"], "https://atcoder.jp/contests/abc999/editorial/12345")

    def test_acceptance_rejects_unvisited_evidence_url(self) -> None:
        spec = json.loads((ROOT / "examples" / "harnesses" / "atcoder_latest_editorial.harness.json").read_text())
        final_result = {
            "contest_id": "abc999",
            "contest_title": "AtCoder Beginner Contest 999",
            "contest_url": "https://atcoder.jp/contests/abc999",
            "editorial_url": "https://atcoder.jp/contests/abc999/editorial",
            "problems": [],
            "evidence": [{"url": "https://atcoder.jp/contests/abc998/editorial", "reason": "wrong"}],
            "webwalk_trace": [{"step": 1, "url": "https://atcoder.jp/contests/abc999/editorial"}],
        }

        with self.assertRaises(ValueError):
            validate_acceptance(final_result, spec)

    def test_model_harness_builder_validates_model_output(self) -> None:
        spec = json.loads(
            (ROOT / "examples" / "harnesses" / "atcoder_problem_editorial_abc220_a.harness.json").read_text()
        )

        built = ModelHarnessBuilder(FakeJsonClient([spec])).build({"name": "atcoder_problem_editorial"})

        self.assertEqual(built["harness_id"], spec["harness_id"])

    def test_model_harness_builder_retries_after_invalid_output(self) -> None:
        spec = json.loads(
            (ROOT / "examples" / "harnesses" / "atcoder_problem_editorial_abc220_a.harness.json").read_text()
        )

        built = ModelHarnessBuilder(FakeJsonClient([{"not": "valid"}, spec])).build({"name": "atcoder_problem_editorial"})

        self.assertEqual(built["harness_id"], spec["harness_id"])

    def test_model_agent_executor_returns_model_json(self) -> None:
        executor = ModelAgentExecutor(FakeJsonClient([{"answer": "ok"}]))

        result = executor.dispatch(
            agent=type(
                "Agent",
                (),
                {
                    "name": "weak_agent",
                    "role": "Answer from context.",
                    "prompt": "Return answer.",
                    "io_schema": {"type": "object"},
                },
            )(),
            input_source={"type": "variable", "data": {"question": "hi"}},
            current_payload={},
        )

        self.assertEqual(result, {"answer": "ok"})

    def test_model_agent_executor_retries_invalid_json(self) -> None:
        executor = ModelAgentExecutor(FakeJsonClient(['{"answer": ', {"answer": "ok"}]))

        result = executor.dispatch(
            agent=type(
                "Agent",
                (),
                {
                    "name": "weak_agent",
                    "role": "Answer from context.",
                    "prompt": "Return answer.",
                    "io_schema": {"type": "object"},
                },
            )(),
            input_source={"type": "variable", "data": {"question": "hi"}},
            current_payload={},
        )

        self.assertEqual(result, {"answer": "ok"})

    def test_chat_config_reads_timeout_from_env(self) -> None:
        old_values = {
            key: os.environ.get(key)
            for key in ["MINIMAX_API_KEY", "MODEL_API_KEY", "MINIMAX_TIMEOUT_SECONDS", "MODEL_TIMEOUT_SECONDS"]
        }
        try:
            os.environ["MINIMAX_API_KEY"] = "test-key"
            os.environ["MINIMAX_TIMEOUT_SECONDS"] = "180"
            os.environ.pop("MODEL_TIMEOUT_SECONDS", None)

            config = ChatConfig.from_env()

            self.assertEqual(config.timeout_seconds, 180)
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class AtCoderFixtureExecutor:
    def dispatch(self, agent, input_source, current_payload):
        tool_result = input_source["data"]["result"]
        page = tool_result["page"]
        observations = list(current_payload.get("_observations", []))
        observations.append(page)
        if len(observations) < 3:
            return {
                "_observations": observations,
                "webwalk_trace": tool_result["webwalk_trace"],
            }

        problem_page, editorial_index_page, editorial_page = observations
        return {
            "contest_id": "abc220",
            "problem_id": "abc220_a",
            "problem_title": problem_page["title"],
            "problem_url": problem_page["url"],
            "editorial_index_url": editorial_index_page["url"],
            "editorial_url": editorial_page["url"],
            "editorial_title": editorial_page["title"],
            "editorial_text_excerpt": editorial_page["text_excerpt"],
            "selection_strategy": "fixture_selected_url",
            "evidence": [
                {
                    "url": problem_page["url"],
                    "reason": "Problem page was observed by Runtime WebWalk.",
                },
                {
                    "url": editorial_index_page["url"],
                    "reason": "Editorial index was observed by Runtime WebWalk.",
                },
                {
                    "url": editorial_page["url"],
                    "reason": "Editorial detail page was observed by Runtime WebWalk.",
                },
            ],
            "webwalk_trace": tool_result["webwalk_trace"],
        }


class AtCoderFixtureWalker:
    def __init__(self) -> None:
        self.pages = []

    def open(self, url: str):
        if url.endswith("/tasks/abc220_a"):
            html = "<html><head><title>A - Find Multiple</title></head><body>Problem A.</body></html>"
        elif url.endswith("/editorial/2700"):
            html = (
                "<html><head><title>Editorial - AtCoder Beginner Contest 220</title></head>"
                "<body>A - Find Multiple Editorial by en_translator. Let Y be the largest multiple.</body></html>"
            )
        else:
            html = "<html><head><title>Editorial - AtCoder Beginner Contest 220</title></head><body>Index.</body></html>"
        page = parse_page(url, html)
        self.pages.append(page)
        return page

    def open_link(self, link_id: int):
        return self.open(self.pages[-1].links[link_id].url)

    def trace(self):
        return [
            {"step": index, "url": page.url, "title": page.title, "links": len(page.links)}
            for index, page in enumerate(self.pages, start=1)
        ]


class LatestEditorialFixtureExecutor:
    def dispatch(self, agent, input_source, current_payload):
        tool_result = input_source["data"]["result"]
        page = tool_result["page"]
        if page["url"].endswith("archive?lang=en"):
            return {
                "contest_id": "abc999",
                "contest_title": "AtCoder Beginner Contest 999",
                "contest_url": "https://atcoder.jp/contests/abc999",
                "editorial_url": "https://atcoder.jp/contests/abc999/editorial",
                "evidence": [
                    {
                        "url": page["url"],
                        "reason": "Archive page was observed by Runtime WebWalk.",
                    }
                ],
                "webwalk_trace": tool_result["webwalk_trace"],
            }
        return {
            **current_payload,
            "problems": [
                {
                    "title": "A - First Problem",
                    "editorial_url": "https://atcoder.jp/contests/abc999/editorial/12345",
                }
            ],
            "evidence": [
                *current_payload["evidence"],
                {
                    "url": page["url"],
                    "reason": "Editorial page was observed by Runtime WebWalk.",
                },
            ],
            "webwalk_trace": tool_result["webwalk_trace"],
        }


class LatestEditorialFixtureWalker:
    def __init__(self) -> None:
        self.pages = []

    def open(self, url: str):
        if url.endswith("archive?lang=en"):
            html = (
                "<html><head><title>Contest Archive</title></head><body>"
                "<a href='/contests/abc999'>AtCoder Beginner Contest 999</a>"
                "</body></html>"
            )
        else:
            html = (
                "<html><head><title>Editorial - ABC999</title></head><body>"
                "<a href='/contests/abc999/editorial/12345'>A - First Problem</a>"
                "</body></html>"
            )
        page = parse_page(url, html)
        self.pages.append(page)
        return page

    def open_link(self, link_id: int):
        return self.open(self.pages[-1].links[link_id].url)

    def trace(self):
        return [
            {"step": index, "url": page.url, "title": page.title, "links": len(page.links)}
            for index, page in enumerate(self.pages, start=1)
        ]


class FakeJsonClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete_json(self, messages):
        response = self._pop_response(messages)
        if isinstance(response, str):
            raise AssertionError("complete_json fake response must be an object")
        return response

    def complete(self, messages):
        response = self._pop_response(messages)
        if isinstance(response, str):
            return response
        return json.dumps(response)

    def _pop_response(self, messages):
        del messages
        if not self.responses:
            raise AssertionError("fake client exhausted")
        return self.responses.pop(0)


if __name__ == "__main__":
    unittest.main()
