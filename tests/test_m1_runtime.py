from __future__ import annotations

import json
import sys
import unittest
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoharness import (
    AutoHarnessError,
    ErrorCode,
    Runtime,
    RuntimeState,
    StaticAgentExecutor,
    validate_action,
)
from autoharness.run_trace import main as run_trace_main
from autoharness.run_trace import run_trace_file


def load_example_trace() -> list[dict]:
    with (ROOT / "examples" / "m1-action-trace.json").open(encoding="utf-8") as handle:
        return json.load(handle)


class M1RuntimeTest(unittest.TestCase):
    def test_schema_rejects_invalid_uuid(self) -> None:
        action = {
            **load_example_trace()[0],
            "action_id": "not-a-uuid",
        }

        with self.assertRaises(AutoHarnessError) as raised:
            validate_action(action)
        self.assertEqual(raised.exception.code, ErrorCode.SCHEMA_INVALID)

    def test_schema_rejects_extra_payload_fields(self) -> None:
        action = {
            **load_example_trace()[0],
            "payload": {
                **load_example_trace()[0]["payload"],
                "unexpected": True,
            },
        }

        with self.assertRaises(AutoHarnessError) as raised:
            validate_action(action)
        self.assertEqual(raised.exception.code, ErrorCode.SCHEMA_INVALID)

    def test_happy_path_example_trace_reaches_done(self) -> None:
        runtime = Runtime(
            executor=StaticAgentExecutor(
                {
                    "draft_agent": {
                        "answer": "Accepted candidate payload.",
                    }
                }
            )
        )

        runtime.run_trace(load_example_trace())

        self.assertEqual(runtime.state, RuntimeState.DONE)
        self.assertEqual(runtime.current_payload, {"answer": "Accepted candidate payload."})
        self.assertIsNone(runtime.temp_buffer)
        self.assertEqual(runtime.final_result, {"answer": "Accepted candidate payload."})

    def test_dispatch_writes_temp_buffer_without_mutating_current_payload(self) -> None:
        runtime = Runtime(
            executor=StaticAgentExecutor({"draft_agent": {"answer": "candidate"}}),
            initial_payload={"answer": "original"},
        )
        plan, create_agent, dispatch, *_ = load_example_trace()

        runtime.apply(plan)
        runtime.apply(create_agent)
        runtime.apply(dispatch)

        self.assertEqual(runtime.state, RuntimeState.AWAITING_ACCEPTANCE)
        self.assertEqual(runtime.current_payload, {"answer": "original"})
        self.assertEqual(runtime.temp_buffer, {"answer": "candidate"})

    def test_accept_commits_temp_buffer(self) -> None:
        runtime = Runtime(executor=StaticAgentExecutor({"draft_agent": {"answer": "candidate"}}))
        plan, create_agent, dispatch, accept, *_ = load_example_trace()

        for action in [plan, create_agent, dispatch, accept]:
            runtime.apply(action)

        self.assertEqual(runtime.state, RuntimeState.EXECUTING)
        self.assertEqual(runtime.current_payload, {"answer": "candidate"})
        self.assertIsNone(runtime.temp_buffer)

    def test_reject_discards_temp_buffer_and_enters_replanning(self) -> None:
        runtime = Runtime(
            executor=StaticAgentExecutor({"draft_agent": {"answer": "candidate"}}),
            initial_payload={"answer": "original"},
        )
        plan, create_agent, dispatch, accept, *_ = load_example_trace()
        reject = {
            **accept,
            "action_id": "66666666-6666-4666-8666-666666666666",
            "payload": {
                "decision": "Reject",
                "reason": "Candidate does not meet quality bar.",
            },
        }

        for action in [plan, create_agent, dispatch, reject]:
            runtime.apply(action)

        self.assertEqual(runtime.state, RuntimeState.REPLANNING)
        self.assertEqual(runtime.current_payload, {"answer": "original"})
        self.assertIsNone(runtime.temp_buffer)

    def test_temp_buffer_lock_rejects_non_accept_actions(self) -> None:
        runtime = Runtime(executor=StaticAgentExecutor({"draft_agent": {"answer": "candidate"}}))
        plan, create_agent, dispatch, _, finish = load_example_trace()

        for action in [plan, create_agent, dispatch]:
            runtime.apply(action)

        with self.assertRaises(AutoHarnessError) as raised:
            runtime.apply(finish)
        self.assertEqual(raised.exception.code, ErrorCode.TEMP_BUFFER_LOCKED)

    def test_invalid_state_transition_is_rejected(self) -> None:
        runtime = Runtime()
        _, create_agent, *_ = load_example_trace()

        with self.assertRaises(AutoHarnessError) as raised:
            runtime.apply(create_agent)
        self.assertEqual(raised.exception.code, ErrorCode.ACTION_NOT_ALLOWED)

    def test_unknown_agent_is_rejected(self) -> None:
        runtime = Runtime()
        plan, _, dispatch, *_ = load_example_trace()

        runtime.apply(plan)
        with self.assertRaises(AutoHarnessError) as raised:
            runtime.apply(dispatch)
        self.assertEqual(raised.exception.code, ErrorCode.AGENT_NOT_FOUND)

    def test_unknown_tool_is_rejected(self) -> None:
        runtime = Runtime()
        plan, create_agent, dispatch, *_ = load_example_trace()
        tool_dispatch = {
            **dispatch,
            "action_id": "77777777-7777-4777-8777-777777777777",
            "payload": {
                "target_agent_name": "draft_agent",
                "input_source": {
                    "type": "tool",
                    "data": {
                        "tool_name": "missing_tool",
                        "arguments": {},
                    },
                },
            },
        }

        runtime.apply(plan)
        runtime.apply(create_agent)
        with self.assertRaises(AutoHarnessError) as raised:
            runtime.apply(tool_dispatch)
        self.assertEqual(raised.exception.code, ErrorCode.TOOL_NOT_FOUND)

    def test_executor_must_return_object(self) -> None:
        class BadExecutor:
            def dispatch(self, agent, input_source, current_payload):
                return "not an object"

        runtime = Runtime(executor=BadExecutor())
        plan, create_agent, dispatch, *_ = load_example_trace()

        runtime.apply(plan)
        runtime.apply(create_agent)
        with self.assertRaises(AutoHarnessError) as raised:
            runtime.apply(dispatch)
        self.assertEqual(raised.exception.code, ErrorCode.SCHEMA_INVALID)

    def test_duplicate_action_id_is_rejected(self) -> None:
        runtime = Runtime()
        plan = load_example_trace()[0]

        runtime.apply(plan)
        with self.assertRaises(AutoHarnessError) as raised:
            runtime.apply(plan)
        self.assertEqual(raised.exception.code, ErrorCode.IDEMPOTENCY_CONFLICT)

    def test_run_trace_file_returns_snapshot(self) -> None:
        snapshot = run_trace_file(ROOT / "examples" / "m1-action-trace.json")

        self.assertEqual(snapshot["state"], "DONE")
        self.assertEqual(snapshot["current_payload"], {"answer": "Accepted candidate payload."})

    def test_run_trace_cli_prints_snapshot_json(self) -> None:
        stdout = StringIO()

        exit_code = run_trace_main(
            [str(ROOT / "examples" / "m1-action-trace.json")],
            stdout=stdout,
        )

        self.assertEqual(exit_code, 0)
        snapshot = json.loads(stdout.getvalue())
        self.assertEqual(snapshot["state"], "DONE")


if __name__ == "__main__":
    unittest.main()
