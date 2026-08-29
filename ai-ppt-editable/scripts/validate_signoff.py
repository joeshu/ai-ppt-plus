#!/usr/bin/env python3
"""Validate structured human closeout sign-off.

Required boolean decisions are narrative, facts, visual, fidelity and brand.
An optional boolean `editability` decision records acceptance of L3/L4
reduced-editability or manual placeholders; it is never implicitly approved.
This validator never creates approval and never treats a missing field as an
implicit yes.
"""
import argparse
import json
from pathlib import Path
from atomic_output import atomic_write_json

REQUIRED = ("narrative", "facts", "visual", "fidelity", "brand")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("signoff")
    parser.add_argument("--report")
    args = parser.parse_args()
    path = Path(args.signoff)
    issues = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/signoff-validation/v1", "valid": False, "status": "invalid", "issues": [{"severity": "blocker", "code": "invalid_json", "message": f"{type(exc).__name__}: {exc}"}]}
        print(json.dumps(result, ensure_ascii=False))
        return 3
    if not isinstance(data, dict):
        issues.append({"severity": "blocker", "code": "signoff_not_object"})
        data = {}
    for field in REQUIRED:
        if field not in data:
            issues.append({"severity": "blocker", "code": "missing_decision", "field": field})
        elif not isinstance(data[field], bool):
            issues.append({"severity": "blocker", "code": "decision_not_boolean", "field": field})
        elif data[field] is not True:
            issues.append({"severity": "blocker", "code": "decision_not_approved", "field": field})
    decisions = {field: data.get(field) for field in REQUIRED}
    if "editability" in data:
        if not isinstance(data["editability"], bool):
            issues.append({"severity": "blocker", "code": "decision_not_boolean", "field": "editability"})
        decisions["editability"] = data["editability"]
    result = {
        "schema": "ai-ppt-plus/signoff-validation/v1",
        "valid": not issues,
        "status": "approved" if not issues else "incomplete",
        "reviewer": data.get("reviewer"),
        "confirmed_at": data.get("confirmed_at"),
        "decisions": decisions,
        "issues": issues,
    }
    if args.report:
        report = Path(args.report)
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
