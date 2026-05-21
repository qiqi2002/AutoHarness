"""Smoke test model-backed strong builder and weak executor adapters."""

from __future__ import annotations

import json
from pathlib import Path

from autoharness.llm import ChatClient, ChatConfig
from autoharness.model_harness import ModelAgentExecutor, ModelHarnessBuilder
from autoharness.runtime import AgentDefinition


def main() -> int:
    task = json.loads(Path("configs/tasks/atcoder_problem_editorial.json").read_text(encoding="utf-8"))
    task["inputs"]["editorial_url"] = "https://atcoder.jp/contests/abc220/editorial/2700"
    client = ChatClient(ChatConfig.from_env())

    spec = ModelHarnessBuilder(client).build(task)
    print(f"strong_builder_harness_id={spec['harness_id']}")

    weak = ModelAgentExecutor(client)
    result = weak.dispatch(
        AgentDefinition(
            name="smoke_weak",
            role="Echo structured smoke result.",
            prompt='Return exactly {"ok": true, "source": "weak_model"}.',
            io_schema={"type": "object"},
        ),
        {"type": "variable", "data": {"smoke": True}},
        {},
    )
    print(f"weak_executor_ok={str(bool(result.get('ok'))).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
