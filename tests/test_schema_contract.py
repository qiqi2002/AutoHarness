from __future__ import annotations

import json
import unittest
from pathlib import Path

from test_m1_runtime import ROOT, load_trace
from autoharness.schema_validation import load_json

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
            "examples/webwalk-tool-action-trace.json",
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

    def test_webwalk_tool_arguments_schema(self) -> None:
        schema = load_json(ROOT / "schemas" / "tools" / "webwalk-tool-arguments.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        valid = {"operation": "open_url", "url": "https://atcoder.jp/contests/abc220"}
        invalid = {"operation": "open_url", "url": "https://atcoder.jp/contests/abc220", "link_id": 0}

        self.assertEqual(list(validator.iter_errors(valid)), [])
        self.assertNotEqual(list(validator.iter_errors(invalid)), [])

    def test_webwalk_planner_action_schema(self) -> None:
        schema = load_json(ROOT / "schemas" / "tools" / "webwalk-planner-action.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        valid = {"action": "open_link", "link_id": 3}
        invalid = {"action": "open_link", "url": "https://atcoder.jp/"}

        self.assertEqual(list(validator.iter_errors(valid)), [])
        self.assertNotEqual(list(validator.iter_errors(invalid)), [])


@unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
class TaskSchemaContractTest(unittest.TestCase):
    def assert_valid_json_file(self, schema_path: str, data_path: str) -> None:
        schema = load_json(ROOT / schema_path)
        data = load_json(ROOT / data_path)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(data), key=lambda error: error.path)
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_recorded_problem_editorial_matches_schema(self) -> None:
        self.assert_valid_json_file(
            "schemas/tasks/atcoder_problem_editorial.schema.json",
            "examples/recorded/atcoder_problem_editorial_abc220_a.json",
        )
