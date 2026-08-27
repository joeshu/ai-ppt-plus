#!/usr/bin/env python3
"""Validate persisted handoff state and approved artifact hashes.

Usage: validate_handoff.py HANDOFF.json [--report REPORT.json]
Exit 0 when recovery inputs are consistent, 2 when a blocker is found,
3 when the handoff cannot be read. Read-only except for the optional report.
"""
import argparse
import hashlib
import json
from pathlib import Path

REQUIRED = (
    "project_id", "revision", "current_stage", "gate_status", "approved_artifacts",
    "completed_slides", "active_batch", "remaining_slides", "open_blockers",
    "repair_round", "latest_checks", "backend", "next_action", "updated_at",
)

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff")
    parser.add_argument("--report")
    args = parser.parse_args()
    path = Path(args.handoff)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"valid": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 3
    issues = []
    for field in REQUIRED:
        if field not in data or data[field] in (None, ""):
            issues.append({"severity": "blocker", "code": "missing_field", "field": field})
    approved = data.get("approved_artifacts") or {}
    for key, value in approved.items():
        if key.endswith("_sha256"):
            continue
        if not isinstance(value, str) or not value:
            issues.append({"severity": "blocker", "code": "invalid_artifact_path", "artifact": key})
        elif not Path(value).is_file():
            issues.append({"severity": "blocker", "code": "artifact_missing", "artifact": key, "path": value})
    pptx = approved.get("pptx")
    expected_hash = approved.get("pptx_sha256")
    if pptx and expected_hash and Path(pptx).is_file():
        observed_hash = sha256(Path(pptx))
        if observed_hash != expected_hash:
            issues.append({"severity": "blocker", "code": "artifact_hash_mismatch", "artifact": "pptx", "expected": expected_hash, "observed": observed_hash})
    if data.get("current_stage") == "delivered" and data.get("open_blockers"):
        issues.append({"severity": "blocker", "code": "delivered_with_open_blockers"})
    if data.get("remaining_slides") and data.get("current_stage") == "delivered":
        issues.append({"severity": "blocker", "code": "delivered_with_remaining_slides"})
    result = {
        "schema": "ai-ppt-plus/handoff-validation/v1",
        "valid": not any(item["severity"] == "blocker" for item in issues),
        "handoff": str(path.resolve()),
        "project_id": data.get("project_id"),
        "revision": data.get("revision"),
        "state": data.get("current_stage"),
        "issues": issues,
    }
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
