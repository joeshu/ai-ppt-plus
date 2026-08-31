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


def resolve_artifact(value, *, base: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff")
    parser.add_argument("--report")
    parser.add_argument("--require-worker-protocol", action="store_true", help="require normalized worker handoff records")
    parser.add_argument("--expected-package-revision", help="block recovery when the handoff was produced by another skill package revision")
    args = parser.parse_args()
    path = Path(args.handoff).resolve()
    base = path.parent
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"valid": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 3
    issues = []
    if not isinstance(data, dict):
        data = {}
        issues.append({"severity": "blocker", "code": "handoff_not_object"})
    schema = data.get("schema")
    if schema not in {None, "ai-ppt-plus/handoff/v1", "ai-ppt-plus/handoff/v2"}:
        issues.append({"severity": "blocker", "code": "invalid_schema", "schema": schema})
    for field in REQUIRED:
        if field not in data or data[field] in (None, ""):
            issues.append({"severity": "blocker", "code": "missing_field", "field": field})
    approved = data.get("approved_artifacts") if isinstance(data.get("approved_artifacts"), dict) else {}
    current_stage = data.get("current_stage")
    capabilities = data.get("capability_status") if isinstance(data.get("capability_status"), dict) else {}
    if current_stage not in STATES:
        issues.append({"severity": "blocker", "code": "invalid_state", "state": current_stage, "allowed": sorted(STATES)})
    if current_stage == "delivered" and data.get("gate_status") not in {"delivered", "release-passed"}:
        issues.append({"severity": "blocker", "code": "delivered_gate_status_invalid", "gate_status": data.get("gate_status")})
    if current_stage == "delivered" and capabilities.get("human_signoff") not in {"passed", "approved", "signed-off", "completed"}:
        issues.append({"severity": "blocker", "code": "delivered_without_human_signoff"})
    if current_stage == "human-closeout" and capabilities.get("human_signoff") not in {"pending", "passed", "approved"}:
        issues.append({"severity": "blocker", "code": "human_closeout_status_invalid"})
    if schema == "ai-ppt-plus/handoff/v2":
        for field in V2_REQUIRED:
            if field not in data or data[field] in (None, "", []):
                issues.append({"severity": "blocker", "code": "missing_v2_field", "field": field})
        if data.get("route") not in ROUTES:
            issues.append({"severity": "blocker", "code": "invalid_route", "route": data.get("route")})
        if args.expected_package_revision and data.get("package_revision") != args.expected_package_revision:
            issues.append({"severity": "blocker", "code": "package_revision_mismatch", "expected": args.expected_package_revision, "observed": data.get("package_revision")})
        if args.require_worker_protocol:
            if data.get("handoff_protocol") != "ai-ppt-plus/worker-handoff/v1":
                issues.append({"severity": "blocker", "code": "worker_protocol_missing"})
            workers = data.get("worker_handoffs") if isinstance(data.get("worker_handoffs"), dict) else {}
            for name in ("visual", "editable"):
                record = workers.get(name)
                if not isinstance(record, dict):
                    issues.append({"severity": "blocker", "code": "worker_handoff_missing", "worker": name})
                    continue
                for field in ("protocol", "skill", "skill_revision", "status", "input_hashes", "output_artifacts", "manifest_paths", "qa_results", "known_issues", "next_action"):
                    if field not in record:
                        issues.append({"severity": "blocker", "code": "worker_handoff_field_missing", "worker": name, "field": field})
                if record.get("protocol") != "ai-ppt-plus/worker-handoff/v1":
                    issues.append({"severity": "blocker", "code": "worker_handoff_protocol_invalid", "worker": name})
                if args.expected_package_revision and record.get("skill_revision") != args.expected_package_revision:
                    issues.append({"severity": "blocker", "code": "worker_revision_mismatch", "worker": name, "expected": args.expected_package_revision, "observed": record.get("skill_revision")})
        artifacts = data.get("artifacts")
        records = artifacts.values() if isinstance(artifacts, dict) else artifacts if isinstance(artifacts, list) else []
        for name, record in (artifacts.items() if isinstance(artifacts, dict) else enumerate(records)):
            if not isinstance(record, dict):
                issues.append({"severity": "blocker", "code": "artifact_record_invalid", "artifact": name})
                continue
            artifact_path = record.get("path")
            declared = record.get("sha256")
            resolved_artifact = resolve_artifact(artifact_path, base=base)
            observed_exists = bool(resolved_artifact and resolved_artifact.is_file())
            if isinstance(record.get("exists"), bool) and record.get("exists") is not observed_exists:
                issues.append({"severity": "blocker", "code": "artifact_existence_mismatch", "artifact": name, "declared": record.get("exists"), "observed": observed_exists})
            if record.get("required") and not observed_exists:
                issues.append({"severity": "blocker", "code": "artifact_missing", "artifact": name, "path": str(resolved_artifact) if resolved_artifact else artifact_path})
            if observed_exists and resolved_artifact is not None:
                if not isinstance(declared, str) or not SHA256_RE.fullmatch(declared):
                    issues.append({"severity": "blocker", "code": "artifact_hash_missing", "artifact": name})
                elif sha256(resolved_artifact) != declared:
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
        approved_path = resolve_artifact(value, base=base)
        if not isinstance(value, str) or not value:
            issues.append({"severity": "blocker", "code": "invalid_artifact_path", "artifact": key})
        elif approved_path is None or not approved_path.is_file():
            issues.append({"severity": "blocker", "code": "artifact_missing", "artifact": key, "path": str(approved_path) if approved_path else value})
        else:
            declared = approved.get(f"{key}_sha256")
            if schema == "ai-ppt-plus/handoff/v2" and (not isinstance(declared, str) or not SHA256_RE.fullmatch(declared)):
                issues.append({"severity": "blocker", "code": "artifact_hash_missing", "artifact": key})
            elif isinstance(declared, str) and SHA256_RE.fullmatch(declared) and sha256(approved_path) != declared:
                issues.append({"severity": "blocker", "code": "artifact_hash_mismatch", "artifact": key, "expected": declared, "observed": sha256(approved_path)})
    pptx = approved.get("pptx")
    expected_hash = approved.get("pptx_sha256")
    pptx_path = resolve_artifact(pptx, base=base)
    if pptx_path and expected_hash and pptx_path.is_file():
        observed_hash = sha256(pptx_path)
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
        "package_revision": data.get("package_revision"),
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
