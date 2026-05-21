from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoharness.harness import require_valid_harness_spec, run_harness_spec
from autoharness.harness_builders import AtCoderProblemEditorialHarnessBuilder
from autoharness.webwalk import WebWalkRuntimeTool, parse_page


class HarnessSpecTest(unittest.TestCase):
    def test_static_atcoder_builder_produces_valid_harness_spec(self) -> None:
        task = json.loads((ROOT / "configs" / "tasks" / "atcoder_problem_editorial.json").read_text())
        task["inputs"]["editorial_url"] = "https://atcoder.jp/contests/abc220/editorial/2700"

        spec = AtCoderProblemEditorialHarnessBuilder().build(task)

        require_valid_harness_spec(spec)
        self.assertEqual(spec["harness_id"], "atcoder-problem-editorial-abc220-abc220_a")
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


if __name__ == "__main__":
    unittest.main()
