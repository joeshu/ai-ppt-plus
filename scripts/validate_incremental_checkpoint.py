#!/usr/bin/env python3
"""Validate a resumable A-O checkpoint without changing it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json
from incremental_orchestrator import CheckpointStore, SCHEMA, STAGE_NAMES, digest


def validate(path: Path, *, strict: bool = False) -> dict:
    issues: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"schema": "ai-ppt-plus/checkpoint-validation/v1", "valid": False, "status": "blocked", "issues": [{"code": "checkpoint_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
    if data.get("schema") != SCHEMA or data.get("schema_version") != 1:
        issues.append({"code": "checkpoint_schema_invalid", "observed": data.get("schema")})
    for name in ("run_id", "repository_sha", "package_revision", "inputs", "fonts", "stages", "artifact_marker", "resume"):
        if name not in data:
            issues.append({"code": "checkpoint_field_missing", "field": name})
    stages = data.get("stages") if isinstance(data.get("stages"), dict) else {}
    missing = sorted(set(STAGE_NAMES) - set(stages))
    if missing:
        issues.append({"code": "checkpoint_stage_missing", "stages": missing})
    for code, stage in stages.items():
        if code not in STAGE_NAMES or not isinstance(stage, dict):
            issues.append({"code": "checkpoint_stage_invalid", "stage": code})
            continue
        if stage.get("status") not in {"pending", "passed", "cached", "failed", "invalidated"}:
            issues.append({"code": "checkpoint_status_invalid", "stage": code})
        if strict and stage.get("status") in {"passed", "cached"}:
            for raw, record in (stage.get("outputs") or {}).items():
                observed = digest(raw) if Path(raw).exists() else None
                expected = record.get("sha256") if isinstance(record, dict) else record
                if observed != expected:
                    issues.append({"code": "checkpoint_output_hash_mismatch", "stage": code, "path": raw, "expected": expected, "observed": observed})
    return {"schema": "ai-ppt-plus/checkpoint-validation/v1", "valid": not issues, "status": "passed" if not issues else "blocked", "checkpoint": str(path), "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    result = validate(Path(args.checkpoint).resolve(), strict=args.strict)
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

