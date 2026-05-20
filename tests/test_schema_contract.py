from __future__ import annotations

import json
import unittest
from pathlib import Path

from test_m1_runtime import ROOT, load_trace

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ModuleNotFoundError:
    Draft202012Validator = None
    FormatChecker = None


@unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
class ActionSchemaContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema_path = ROOT / "schemas" / "action-envelope.schema.json"
        cls.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def assert_valid_action(self, action: dict) -> None:
        errors = sorted(self.validator.iter_errors(action), key=lambda error: error.path)
        self.assertEqual(errors, [], [error.message for error in errors])

    def assert_invalid_action(self, action: dict) -> None:
        errors = list(self.validator.iter_errors(action))
        self.assertNotEqual(errors, [])

    def test_all_example_trace_actions_match_schema(self) -> None:
        traces = [
            "examples/m1-action-trace.json",
            "examples/tool-action-trace.json",
            "examples/invalid/finish-before-accept.json",
            "examples/invalid/finish-result-mismatch.json",
        ]

        for trace_path in traces:
            with self.subTest(trace=trace_path):
                for action in load_trace(trace_path):
                    self.assert_valid_action(action)

    def test_schema_rejects_invalid_uuid(self) -> None:
        action = {
            **load_trace("examples/m1-action-trace.json")[0],
            "action_id": "not-a-uuid",
        }

        self.assert_invalid_action(action)

    def test_schema_rejects_tool_data_without_arguments(self) -> None:
        action = load_trace("examples/tool-action-trace.json")[2]
        action = {
            **action,
            "payload": {
                "target_agent_name": "tool_agent",
                "input_source": {
                    "type": "tool",
                    "data": {
                        "tool_name": "echo",
                    },
                },
            },
        }

        self.assert_invalid_action(action)
