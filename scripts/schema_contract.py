#!/usr/bin/env python3
"""Dependency-free subset of JSON Schema used by repository contract tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate(instance: Any, schema: dict[str, Any], path: str = "$", errors: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    errors = errors if errors is not None else []
    expected = schema.get("type")
    type_ok = {
        "object": isinstance(instance, dict),
        "array": isinstance(instance, list),
        "string": isinstance(instance, str),
        "boolean": isinstance(instance, bool),
        "number": isinstance(instance, (int, float)) and not isinstance(instance, bool),
        "integer": isinstance(instance, int) and not isinstance(instance, bool),
        "null": instance is None,
    }
    if isinstance(expected, list):
        matches = any(type_ok.get(item, True) for item in expected)
    else:
        matches = type_ok.get(expected, True)
    if not matches:
        errors.append({"path": path, "code": "type", "message": f"expected {expected}"})
        return errors
    if "enum" in schema and instance not in schema["enum"]:
        errors.append({"path": path, "code": "enum", "message": f"value is not one of {schema['enum']}"})
    if isinstance(instance, dict):
        for field in schema.get("required", []):
            if field not in instance:
                errors.append({"path": path, "code": "required", "message": f"missing {field}"})
        for key, value in instance.items():
            child_schema = schema.get("properties", {}).get(key)
            if child_schema:
                validate(value, child_schema, f"{path}.{key}", errors)
    if isinstance(instance, list):
        minimum = schema.get("minItems")
        if minimum is not None and len(instance) < minimum:
            errors.append({"path": path, "code": "minItems", "message": f"expected at least {minimum} items"})
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                validate(value, item_schema, f"{path}[{index}]", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schema")
    parser.add_argument("instance")
    args = parser.parse_args()
    try:
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
        instance = json.loads(Path(args.instance).read_text(encoding="utf-8"))
        issues = validate(instance, schema)
    except Exception as exc:
        issues = [{"path": "$", "code": "read_error", "message": f"{type(exc).__name__}: {exc}"}]
    result = {"schema": "ai-ppt-plus/schema-validation/v1", "valid": not issues, "schema_file": str(Path(args.schema).resolve()), "instance_file": str(Path(args.instance).resolve()), "issues": issues}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
