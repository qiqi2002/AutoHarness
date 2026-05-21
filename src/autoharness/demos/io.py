"""Shared CLI helpers for demo tasks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from autoharness.schema_validation import require_valid_with_schema


def emit_result(
    result: dict[str, Any],
    *,
    output: str | None,
    schema_path: str | None,
) -> None:
    if schema_path:
        require_valid_with_schema(result, schema_path)

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(rendered + "\n", encoding="utf-8")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(rendered)
