"""Local trace runner for M1 testing and conformance checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, TextIO

from autoharness.runtime import Runtime, StaticAgentExecutor
from autoharness.webwalk import WebWalkRuntimeTool, parse_page


def load_trace(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise ValueError("trace file must contain a JSON array")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError("trace file must contain only JSON objects")
    return value


def run_trace_file(path: str | Path) -> dict[str, Any]:
    """Run a trace file with the deterministic M1 test executor."""

    runtime = Runtime(
        executor=StaticAgentExecutor(
            {
                "draft_agent": {
                    "answer": "Accepted candidate payload.",
                },
                "tool_agent": {
                    "answer": "Tool-backed accepted payload.",
                },
                "observation_agent": {
                    "visited_url": "https://atcoder.jp/contests/abc220/tasks/abc220_a",
                    "page_title": "A - Find Multiple",
                    "trace_length": 1,
                },
            }
        ),
        tools={
            "echo": lambda arguments: dict(arguments),
            "webwalk": WebWalkRuntimeTool(_TraceFixtureWalker()),
        },
    )
    runtime.run_trace(load_trace(path))
    return runtime.snapshot()


class _TraceFixtureWalker:
    """Deterministic WebWalk fixture for local trace conformance runs."""

    def __init__(self) -> None:
        self.pages = []

    def open(self, url: str):
        page = parse_page(
            url,
            "<html><head><title>A - Find Multiple</title></head><body>Problem A.</body></html>",
        )
        self.pages.append(page)
        return page

    def open_link(self, link_id: int):
        return self.open(self.pages[-1].links[link_id].url)

    def trace(self):
        return [
            {"step": index, "url": page.url, "title": page.title, "links": len(page.links)}
            for index, page in enumerate(self.pages, start=1)
        ]


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an AutoHarness Action trace.")
    parser.add_argument("trace", help="Path to a JSON trace file.")
    args = parser.parse_args(argv)

    output = stdout
    if output is None:
        import sys

        output = sys.stdout

    snapshot = run_trace_file(args.trace)
    json.dump(snapshot, output, ensure_ascii=False, indent=2)
    output.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
