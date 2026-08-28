#!/usr/bin/env python3
"""Normalize child reports into one deterministic project-level report."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from report_envelope import normalize_child


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_index")
    parser.add_argument("--report", required=True)
    parser.add_argument("--require-all", action="store_true", help="treat every indexed report as required")
    args = parser.parse_args()
    index_path = Path(args.report_index).resolve()
    index, error = read_json(index_path)
    if error:
        result = {"schema": "ai-ppt-plus/report-envelope/v1", "report_type": "project-aggregate", "valid": False, "status": "invalid", "issues": [{"severity": "blocker", "code": "report_index_invalid", "message": error}]}
        print(json.dumps(result, ensure_ascii=False))
        return 3
    issues = []
    if not isinstance(index, dict):
        index = {}
        issues.append({"severity": "blocker", "code": "report_index_not_object"})
    if index.get("schema") != "ai-ppt-plus/report-index/v1":
        issues.append({"severity": "blocker", "code": "report_index_schema_invalid", "observed": index.get("schema")})
    for field in ("project_id", "revision", "stage", "deck_path", "deck_sha256"):
        if not isinstance(index.get(field), str) or not index.get(field).strip():
            issues.append({"severity": "blocker", "code": "report_index_field_missing", "field": field})
    reports = index.get("reports", [])
    if not isinstance(reports, list) or not reports:
        issues.append({"severity": "blocker", "code": "report_index_empty"})
        reports = []
    report_evidence = []
    input_hashes = {}
    required_failures = 0
    optional_failures = 0
    component_usage = None
    for position, entry in enumerate(reports):
        if not isinstance(entry, dict):
            issues.append({"severity": "blocker", "code": "report_entry_not_object", "index": position})
            continue
        report_type = entry.get("report_type")
        report_path_value = entry.get("path")
        required = args.require_all or entry.get("required") is True
        if not isinstance(report_type, str) or not report_type.strip():
            issues.append({"severity": "blocker", "code": "report_type_missing", "index": position})
            report_type = f"unknown-{position}"
        if not isinstance(report_path_value, str) or not report_path_value.strip():
            issue = {"severity": "blocker" if required else "major", "code": "report_path_missing", "report_type": report_type}
            issues.append(issue)
            if required:
                required_failures += 1
            else:
                optional_failures += 1
            continue
        report_path = (index_path.parent / report_path_value).resolve()
        evidence = {"report_type": report_type, "path": str(report_path), "required": required, "stage": entry.get("stage")}
        if not report_path.is_file():
            issue = {"severity": "blocker" if required else "major", "code": "report_missing", "report_type": report_type, "path": str(report_path)}
            issues.append(issue)
            evidence.update(normalize_child(report_type, report_path, None, required=required, stage=entry.get("stage"), deck_sha256=index.get("deck_sha256")))
            if required:
                required_failures += 1
            else:
                optional_failures += 1
            report_evidence.append(evidence)
            continue
        report, error = read_json(report_path)
        report_hash = sha256(report_path)
        input_hashes[report_type] = report_hash
        if error or not isinstance(report, dict):
            issues.append({"severity": "blocker" if required else "major", "code": "report_invalid", "report_type": report_type, "message": error or "report must be an object"})
            evidence.update(normalize_child(report_type, report_path, None, required=required, stage=entry.get("stage"), deck_sha256=index.get("deck_sha256")))
            evidence.update({"present": True, "valid": False, "status": "invalid", "native_status": "invalid", "sha256": report_hash})
            if required:
                required_failures += 1
            else:
                optional_failures += 1
            report_evidence.append(evidence)
            continue
        if entry.get("step_ok") is False:
            child_valid = False
        else:
            child_valid = report.get("valid") if isinstance(report.get("valid"), bool) else report.get("ok") if isinstance(report.get("ok"), bool) else entry.get("step_ok") if isinstance(entry.get("step_ok"), bool) else None
        child_status = report.get("status") or ("passed" if child_valid else "failed" if child_valid is False else "legacy")
        child_issues = report.get("issues", report.get("errors", []))
        if isinstance(report.get("component_usage"), dict):
            component_usage = report["component_usage"]
        normalized_report = report if isinstance(report.get("valid"), bool) or isinstance(report.get("ok"), bool) else {**report, "valid": child_valid}
        evidence.update(normalize_child(report_type, report_path, normalized_report, required=required, stage=entry.get("stage"), deck_sha256=index.get("deck_sha256")))
        evidence.update({"present": True, "valid": child_valid, "native_status": report.get("status"), "schema": report.get("schema"), "sha256": report_hash, "issues": child_issues})
        if child_valid is not True:
            severity = "blocker" if required else "major"
            issues.append({"severity": severity, "code": "required_report_failed" if required else "optional_report_failed", "report_type": report_type, "path": str(report_path), "child_status": child_status, "child_issues": child_issues})
            if required:
                required_failures += 1
            else:
                optional_failures += 1
        report_deck_hash = report.get("deck_sha256")
        if index.get("deck_sha256") and report_deck_hash and report_deck_hash != index.get("deck_sha256"):
            issues.append({"severity": "blocker", "code": "child_report_deck_hash_mismatch", "report_type": report_type, "expected": index.get("deck_sha256"), "observed": report_deck_hash})
        report_evidence.append(evidence)
    valid = not any(item.get("severity") == "blocker" for item in issues)
    status = "passed" if valid and not optional_failures else "degraded" if valid else "failed"
    result = {
        "schema": "ai-ppt-plus/report-envelope/v1",
        "report_type": "project-aggregate",
        "project_id": index.get("project_id"),
        "revision": index.get("revision"),
        "stage": index.get("stage", "validated"),
        "validation_scope": index.get("validation_scope", "full"),
        "full_deck_validation_required": index.get("validation_scope", "full") != "full",
        "valid": valid,
        "status": status,
        "technical_valid": valid,
        "technical_status": "passed" if valid else "failed",
        "human_review_required": True,
        "human_review_status": "pending",
        "release_eligible": False,
        "release_status": "blocked-pending-signoff",
        "deck_path": index.get("deck_path"),
        "deck_sha256": index.get("deck_sha256"),
        "report_index_path": str(index_path),
        "report_index_sha256": sha256(index_path),
        "input_hashes": input_hashes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": "ai-ppt-plus/aggregate_project_reports.py",
        "reports_total": len(reports),
        "required_failures": required_failures,
        "optional_failures": optional_failures,
        "component_usage": component_usage,
        "requires_human_closeout": True,
        "may_claim_complete": False,
        "next_state": "validated" if valid else "revision-required",
        "issues": issues,
        "evidence": {"reports": report_evidence},
        "source_references": list(index.get("source_references") or []) + [item.get("source") for item in report_evidence if isinstance(item, dict) and item.get("source")],
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
