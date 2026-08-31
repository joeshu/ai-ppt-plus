#!/usr/bin/env python3
"""Validate structured issue records and their regression closure evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SEVERITIES = {"info", "minor", "major", "critical", "blocker"}
OPEN = {"open", "in-progress", "revision-required"}
CLOSED = {"closed", "fixed", "accepted"}
REQUIRED = ("id", "severity", "status", "owner", "trigger", "root_cause", "fix", "regression_test", "affected_stages")


def validate(path: Path, *, strict: bool = False) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"schema": "ai-ppt-plus/issue-log-validation/v1", "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "issue_log_unreadable", "message": str(exc)}]}
    if not isinstance(data, dict) or data.get("schema") != "ai-ppt-plus/issue-log/v1":
        issues.append({"severity": "blocker", "code": "issue_log_schema_invalid"})
    records = data.get("issues") if isinstance(data, dict) else None
    if not isinstance(records, list):
        issues.append({"severity": "blocker", "code": "issue_log_issues_invalid"})
        records = []
    seen: set[str] = set()
    open_count = 0
    closed_count = 0
    for index, record in enumerate(records):
        prefix = f"issues[{index}]"
        if not isinstance(record, dict):
            issues.append({"severity": "blocker", "code": "issue_record_not_object", "path": prefix})
            continue
        issue_id = record.get("id")
        if not isinstance(issue_id, str) or not issue_id.strip() or issue_id in seen:
            issues.append({"severity": "blocker", "code": "issue_id_missing_or_duplicate", "path": prefix, "id": issue_id})
        else:
            seen.add(issue_id)
        severity = record.get("severity")
        status = record.get("status", "open")
        if severity not in SEVERITIES:
            issues.append({"severity": "blocker", "code": "issue_severity_invalid", "path": prefix})
        if status not in OPEN | CLOSED:
            issues.append({"severity": "blocker", "code": "issue_status_invalid", "path": prefix})
        if status in OPEN:
            open_count += 1
        else:
            closed_count += 1
        for field in REQUIRED:
            if field != "status" and (field not in record or record.get(field) in (None, "", [])):
                issues.append({"severity": "blocker", "code": "issue_field_missing", "path": prefix, "field": field})
        if not isinstance(record.get("affected_stages"), list) or not record.get("affected_stages"):
            issues.append({"severity": "blocker", "code": "issue_affected_stages_invalid", "path": prefix})
        if status in CLOSED and not record.get("resolved_revision"):
            issues.append({"severity": "blocker", "code": "closed_issue_resolution_missing", "path": prefix})
        regression_test = record.get("regression_test")
        if severity in {"critical", "blocker"} and status in CLOSED and (not isinstance(regression_test, str) or not regression_test.strip()):
            issues.append({"severity": "blocker", "code": "closed_critical_regression_missing", "path": prefix})
    if strict and open_count:
        issues.append({"severity": "blocker", "code": "open_issues_block_strict", "count": open_count})
    valid = not any(item.get("severity") == "blocker" for item in issues)
    return {"schema": "ai-ppt-plus/issue-log-validation/v1", "valid": valid, "status": "passed" if valid else "blocked", "project_id": data.get("project_id") if isinstance(data, dict) else None, "revision": data.get("revision") if isinstance(data, dict) else None, "open_count": open_count, "closed_count": closed_count, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue_log")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    result = validate(Path(args.issue_log).resolve(), strict=args.strict)
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
