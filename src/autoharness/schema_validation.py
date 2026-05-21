"""JSON Schema validation helpers used by demos and tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_with_schema(data: Any, schema: dict[str, Any]) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ModuleNotFoundError as exc:
        raise RuntimeError("jsonschema is required for schema validation") from exc

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    return [format_error(error) for error in errors]


def require_valid_with_schema(data: Any, schema_path: str | Path) -> None:
    errors = validate_with_schema(data, load_json(schema_path))
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"schema validation failed:\n{joined}")


def format_error(error: Any) -> str:
    path = ".".join(str(part) for part in error.path)
    location = path or "$"
    return f"{location}: {error.message}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate JSON data against a JSON Schema.")
    parser.add_argument("schema", help="Path to JSON Schema file.")
    parser.add_argument("data", help="Path to JSON data file.")
    args = parser.parse_args(argv)

    errors = validate_with_schema(load_json(args.data), load_json(args.schema))
    if errors:
        for error in errors:
            print(error)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
