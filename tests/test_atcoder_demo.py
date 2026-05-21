from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoharness.demos.atcoder_latest_editorial import (
    build_result,
    find_editorial_links,
    find_latest_finished_contest,
)
from autoharness.llm import ChatConfig, extract_json_object, strip_think_blocks
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


if __name__ == "__main__":
    unittest.main()
