"""Local trace runner for M1 testing and conformance checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, TextIO

from autoharness.runtime import Runtime, StaticAgentExecutor


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
                }
            }
        ),
        tools={
            "echo": lambda arguments: dict(arguments),
        },
    )
    runtime.run_trace(load_trace(path))
    return runtime.snapshot()


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
