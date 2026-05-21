from __future__ import annotations

import json
import sys
import unittest
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoharness.demos.atcoder_latest_editorial import (
    build_result,
    find_editorial_links,
    find_latest_finished_contest,
)
from autoharness.demos.atcoder_problem_editorial import (
    ProblemRequest,
    build_result as build_problem_result,
    editorial_links,
    extract_problem_title,
    problem_index,
    problem_letter,
    select_editorial_candidate,
)
from autoharness.demos.agentic_webwalk import AgenticRunConfig, ScriptedPlanner, run_agentic_webwalk
from autoharness.llm import ChatConfig, extract_json_object, strip_think_blocks
from autoharness.demos.io import emit_result
from autoharness.webwalk import WebWalkTool, parse_page


ARCHIVE_HTML = """
<html><head><title>Contest Archive</title></head>
<body>
<table><tbody>
<tr><td><a href="/contests/abc999">AtCoder Beginner Contest 999</a></td></tr>
<tr><td><a href="/contests/arc999">AtCoder Regular Contest 999</a></td></tr>
</tbody></table>
</body></html>
"""

EDITORIAL_HTML = """
<html><head><title>Editorial - ABC999</title></head>
<body>
<a href="/contests/abc999/editorial/12345">A - First Problem</a>
<a href="/contests/abc999/editorial/12346">B - Second Problem</a>
</body></html>
"""

PROBLEM_HTML = """
<html><head><title>A - Find Multiple - AtCoder Beginner Contest 220</title></head>
<body><h2>A - Find Multiple</h2></body></html>
"""

PROBLEM_EDITORIAL_INDEX_HTML = """
<html><head><title>Editorial - ABC220</title></head>
<body>
<a href="/contests/abc220/editorial/2707">Editorial</a>
<a href="/contests/abc220/editorial/2708">Editorial</a>
<a href="/contests/abc220/editorial/2709">Editorial</a>
</body></html>
"""


class AtCoderDemoTest(unittest.TestCase):
    def test_finds_latest_finished_contest_from_archive_page(self) -> None:
        page = parse_page("https://atcoder.jp/contests/archive?lang=en", ARCHIVE_HTML)

        contest = find_latest_finished_contest(page)

        self.assertEqual(contest.contest_id, "abc999")
        self.assertEqual(contest.title, "AtCoder Beginner Contest 999")
        self.assertEqual(contest.url, "https://atcoder.jp/contests/abc999")

    def test_finds_editorial_links(self) -> None:
        page = parse_page("https://atcoder.jp/contests/abc999/editorial", EDITORIAL_HTML)

        links = find_editorial_links(page, "abc999")

        self.assertEqual(len(links), 2)
        self.assertEqual(links[0]["title"], "A - First Problem")

    def test_build_result_shape(self) -> None:
        archive = parse_page("https://atcoder.jp/contests/archive?lang=en", ARCHIVE_HTML)
        editorial = parse_page("https://atcoder.jp/contests/abc999/editorial", EDITORIAL_HTML)
        contest = find_latest_finished_contest(archive)

        result = build_result(contest, editorial, find_editorial_links(editorial, "abc999"), [])

        self.assertEqual(result["contest_id"], "abc999")
        self.assertIn("evidence", result)
        self.assertIn("webwalk_trace", result)

    def test_webwalk_rejects_disallowed_domain(self) -> None:
        tool = WebWalkTool(allowed_domains=["atcoder.jp"])

        with self.assertRaises(Exception):
            tool.open("https://example.com/")

    def test_strips_model_think_blocks_and_extracts_json(self) -> None:
        raw = '<think>hidden</think>\n```json\n{"ok": true}\n```'

        cleaned = strip_think_blocks(raw)
        parsed = extract_json_object(cleaned)

        self.assertEqual(parsed, {"ok": True})

    def test_chat_config_reads_insecure_tls_flag(self) -> None:
        import os

        old_key = os.environ.get("MINIMAX_API_KEY")
        old_flag = os.environ.get("AUTOHARNESS_LLM_INSECURE_TLS")
        try:
            os.environ["MINIMAX_API_KEY"] = "test-key"
            os.environ["AUTOHARNESS_LLM_INSECURE_TLS"] = "1"
            self.assertTrue(ChatConfig.from_env().insecure_tls)
        finally:
            if old_key is None:
                os.environ.pop("MINIMAX_API_KEY", None)
            else:
                os.environ["MINIMAX_API_KEY"] = old_key
            if old_flag is None:
                os.environ.pop("AUTOHARNESS_LLM_INSECURE_TLS", None)
            else:
                os.environ["AUTOHARNESS_LLM_INSECURE_TLS"] = old_flag

    def test_task_config_is_valid_json(self) -> None:
        config = json.loads((ROOT / "configs" / "tasks" / "atcoder_latest_editorial.json").read_text())

        self.assertEqual(config["name"], "atcoder_latest_editorial")

    def test_extracts_specific_problem_title(self) -> None:
        page = parse_page("https://atcoder.jp/contests/abc220/tasks/abc220_a", PROBLEM_HTML)

        self.assertEqual(extract_problem_title(page, "abc220_a"), "A - Find Multiple")

    def test_problem_letter_and_index(self) -> None:
        self.assertEqual(problem_letter("abc220_a"), "A")
        self.assertEqual(problem_letter("abc220_c"), "C")
        self.assertEqual(problem_index("abc220_c"), 2)

    def test_selects_nth_official_editorial_candidate(self) -> None:
        page = parse_page("https://atcoder.jp/contests/abc220/editorial", PROBLEM_EDITORIAL_INDEX_HTML)

        candidate = select_editorial_candidate(
            page,
            contest_id="abc220",
            problem_id="abc220_b",
            problem_title="B - Base K",
        )

        self.assertEqual(candidate.url, "https://atcoder.jp/contests/abc220/editorial/2708")
        self.assertEqual(candidate.strategy, "nth_official_english_editorial")

    def test_specific_problem_result_shape(self) -> None:
        problem_page = parse_page("https://atcoder.jp/contests/abc220/tasks/abc220_a", PROBLEM_HTML)
        index_page = parse_page("https://atcoder.jp/contests/abc220/editorial", PROBLEM_EDITORIAL_INDEX_HTML)
        candidate = select_editorial_candidate(
            index_page,
            contest_id="abc220",
            problem_id="abc220_a",
            problem_title="A - Find Multiple",
        )
        editorial_page = parse_page(candidate.url, "<html><head><title>Editorial</title></head><body>Use multiples.</body></html>")

        result = build_problem_result(
            request=ProblemRequest("abc220", "abc220_a"),
            problem_title="A - Find Multiple",
            candidate=candidate,
            problem_page=problem_page,
            editorial_index_page=index_page,
            editorial_page=editorial_page,
            trace=[],
        )

        self.assertEqual(result["contest_id"], "abc220")
        self.assertEqual(result["problem_id"], "abc220_a")
        self.assertEqual(result["editorial_url"], "https://atcoder.jp/contests/abc220/editorial/2707")
        self.assertIn("editorial_text_excerpt", result)

    def test_specific_problem_config_is_valid_json(self) -> None:
        config = json.loads((ROOT / "configs" / "tasks" / "atcoder_problem_editorial.json").read_text())

        self.assertEqual(config["name"], "atcoder_problem_editorial")
        self.assertEqual(config["inputs"]["problem_id"], "abc220_a")

    def test_emit_result_writes_json_output(self) -> None:
        result = json.loads((ROOT / "examples" / "recorded" / "atcoder_problem_editorial_abc220_a.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"

            with redirect_stdout(StringIO()):
                emit_result(result, output=str(output), schema_path=None)

            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["problem_id"], "abc220_a")

    def test_agentic_webwalk_with_scripted_planner(self) -> None:
        class FakeWalker:
            def __init__(self) -> None:
                self.pages = []

            def open(self, url):
                if url.endswith("/tasks/abc220_a"):
                    page = parse_page(url, PROBLEM_HTML)
                elif url.endswith("/editorial"):
                    page = parse_page(url, PROBLEM_EDITORIAL_INDEX_HTML)
                else:
                    page = parse_page(url, "<html><head><title>Editorial</title></head><body>A - Find Multiple editorial text.</body></html>")
                self.pages.append(page)
                return page

            def open_link(self, link_id):
                return self.open(self.pages[-1].links[link_id].url)

            def trace(self):
                return [
                    {"step": index, "url": page.url, "title": page.title, "links": len(page.links)}
                    for index, page in enumerate(self.pages, start=1)
                ]

        planner = ScriptedPlanner(
            [
                {"action": "open_url", "url": "https://atcoder.jp/contests/abc220/tasks/abc220_a"},
                {"action": "open_url", "url": "https://atcoder.jp/contests/abc220/editorial"},
                {"action": "open_link", "link_id": 0},
                {
                    "action": "final",
                    "result": {
                        "contest_id": "abc220",
                        "problem_id": "abc220_a",
                        "problem_title": "A - Find Multiple",
                        "problem_url": "https://atcoder.jp/contests/abc220/tasks/abc220_a",
                        "editorial_index_url": "https://atcoder.jp/contests/abc220/editorial",
                        "editorial_url": "https://atcoder.jp/contests/abc220/editorial/2707",
                        "editorial_title": "Editorial",
                        "editorial_text_excerpt": "A - Find Multiple editorial text.",
                        "evidence": ["https://atcoder.jp/contests/abc220/editorial/2707"],
                        "webwalk_trace": ["model should not control runtime trace"],
                    },
                },
            ]
        )

        result = run_agentic_webwalk(
            AgenticRunConfig("abc220", "abc220_a", max_steps=5, use_schema_validation=True),
            planner=planner,
            walker=FakeWalker(),
        )

        self.assertEqual(result["problem_id"], "abc220_a")
        self.assertEqual(len(result["webwalk_trace"]), 3)
        self.assertEqual(result["evidence"][0]["url"], "https://atcoder.jp/contests/abc220/editorial/2707")
        self.assertEqual(result["agentic_action_trace"][2]["action"]["action"], "open_link")


if __name__ == "__main__":
    unittest.main()
