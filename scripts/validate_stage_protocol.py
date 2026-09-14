#!/usr/bin/env python3
"""Validate that the unified A–O protocol has complete stage metadata."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json
from incremental_orchestrator import STAGE_NAMES, stage_protocol


REQUIRED = {"code", "stage", "inputs", "outputs", "retry", "cacheable", "parallel", "recovery"}


def validate() -> dict:
    records = stage_protocol()
    issues = []
    observed = [item.get("code") for item in records]
    if observed != list(STAGE_NAMES):
        issues.append({"code": "stage_order_invalid", "expected": list(STAGE_NAMES), "observed": observed})
    for item in records:
        missing = sorted(REQUIRED - set(item))
        if missing:
            issues.append({"code": "stage_metadata_missing", "stage": item.get("code"), "fields": missing})
        if not isinstance(item.get("inputs"), list) or not isinstance(item.get("outputs"), list):
            issues.append({"code": "stage_io_invalid", "stage": item.get("code")})
        if not isinstance(item.get("cacheable"), bool) or not isinstance(item.get("parallel"), bool):
            issues.append({"code": "stage_execution_flags_invalid", "stage": item.get("code")})
    return {"schema": "ai-ppt-plus/stage-protocol-validation/v1", "valid": not issues, "status": "passed" if not issues else "blocked", "stage_count": len(records), "stages": records, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report")
    args = parser.parse_args()
    result = validate()
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

