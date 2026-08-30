#!/usr/bin/env python3
"""Validate persisted handoff state and approved artifact hashes.

Usage: validate_handoff.py HANDOFF.json [--report REPORT.json]
Exit 0 when recovery inputs are consistent, 2 when a blocker is found,
3 when the handoff cannot be read. Read-only except for the optional report.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from atomic_output import atomic_write_json

REQUIRED = (
    "project_id", "revision", "current_stage", "gate_status", "approved_artifacts",
    "completed_slides", "active_batch", "remaining_slides", "open_blockers",
    "repair_round", "latest_checks", "backend", "next_action", "updated_at",
)
V2_REQUIRED = ("run_id", "package_revision", "route", "artifacts", "cross_artifact", "worker_handoffs")
ROUTES = {"visual-creation", "reference-reconstruction", "native-authoring"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

STATES = {
    "intake", "source-analyzed", "outline-draft", "outline-review",
    "narrative-approved", "design-system-ready", "visual-draft",
    "visual-approved", "reconstruction", "rendered", "validated",
    "revision-required", "human-closeout", "delivered",
}

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
    schema = data.get("schema") if isinstance(data, dict) else None
    if schema not in {None, "ai-ppt-plus/handoff/v1", "ai-ppt-plus/handoff/v2"}:
        issues.append({"severity": "blocker", "code": "invalid_schema", "schema": schema})
    for field in REQUIRED:
        if field not in data or data[field] in (None, ""):
            issues.append({"severity": "blocker", "code": "missing_field", "field": field})
    approved = data.get("approved_artifacts") or {}
    current_stage = data.get("current_stage")
    if current_stage not in STATES:
        issues.append({"severity": "blocker", "code": "invalid_state", "state": current_stage, "allowed": sorted(STATES)})
    if current_stage == "delivered" and data.get("gate_status") not in {"delivered", "release-passed"}:
        issues.append({"severity": "blocker", "code": "delivered_gate_status_invalid", "gate_status": data.get("gate_status")})
    if current_stage == "human-closeout" and not data.get("capability_status", {}).get("human_signoff") in {"pending", "passed", "approved"}:
        issues.append({"severity": "blocker", "code": "human_closeout_status_invalid"})
    if schema == "ai-ppt-plus/handoff/v2":
        for field in V2_REQUIRED:
            if field not in data or data[field] in (None, "", []):
                issues.append({"severity": "blocker", "code": "missing_v2_field", "field": field})
        if data.get("route") not in ROUTES:
            issues.append({"severity": "blocker", "code": "invalid_route", "route": data.get("route")})
        artifacts = data.get("artifacts")
        records = artifacts.values() if isinstance(artifacts, dict) else artifacts if isinstance(artifacts, list) else []
        for name, record in (artifacts.items() if isinstance(artifacts, dict) else enumerate(records)):
            if not isinstance(record, dict):
                issues.append({"severity": "blocker", "code": "artifact_record_invalid", "artifact": name})
                continue
            artifact_path = record.get("path")
            declared = record.get("sha256")
            if record.get("required") and (not isinstance(artifact_path, str) or not Path(artifact_path).is_file()):
                issues.append({"severity": "blocker", "code": "artifact_missing", "artifact": name, "path": artifact_path})
            if isinstance(artifact_path, str) and Path(artifact_path).is_file():
                if not isinstance(declared, str) or not SHA256_RE.fullmatch(declared):
                    issues.append({"severity": "blocker", "code": "artifact_hash_missing", "artifact": name})
                elif sha256(Path(artifact_path)) != declared:
                    issues.append({"severity": "blocker", "code": "artifact_hash_mismatch", "artifact": name})
        cross = data.get("cross_artifact") if isinstance(data.get("cross_artifact"), dict) else {}
        coverage = cross.get("page_coverage") if isinstance(cross.get("page_coverage"), dict) else {}
        expected_pages = cross.get("expected_pages")
        if not isinstance(expected_pages, int) or expected_pages < 1:
            issues.append({"severity": "blocker", "code": "expected_pages_invalid"})
        else:
            completed = set(coverage.get("completed") or [])
            remaining = set(coverage.get("remaining") or [])
            if completed & remaining:
                issues.append({"severity": "blocker", "code": "page_coverage_overlap"})
            covered = sorted(completed | remaining)
            if covered != list(range(1, expected_pages + 1)):
                issues.append({"severity": "blocker", "code": "page_coverage_incomplete", "expected": list(range(1, expected_pages + 1)), "observed": covered})
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
        "schema": "ai-ppt-plus/handoff-validation/v2" if schema == "ai-ppt-plus/handoff/v2" else "ai-ppt-plus/handoff-validation/v1",
        "valid": not any(item["severity"] == "blocker" for item in issues),
        "handoff": str(path.resolve()),
        "project_id": data.get("project_id"),
        "revision": data.get("revision"),
        "state": data.get("current_stage"),
        "issues": issues,
    }
    if args.report:
        report = Path(args.report)
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
