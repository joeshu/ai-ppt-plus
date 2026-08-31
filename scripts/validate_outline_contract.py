#!/usr/bin/env python3
"""Validate the versioned outline master contract and its source bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from atomic_output import atomic_write_json
from validate_outline import FIELDS, STATES, TYPES, read_rows

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_digest(row: dict) -> str:
    payload = {key: str(row.get(key) or "") for key in (
        "slide_no", "section", "title", "core_message", "purpose",
        "body_content", "data_sources", "visual_type", "audience_takeaway",
        "owner_notes", "status", "revision_reason",
    )}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract")
    parser.add_argument("--report")
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    path = Path(args.contract).resolve()
    issues = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/outline-contract-validation/v1", "valid": False, "issues": [{"severity": "blocker", "code": "contract_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
        if args.report: atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False)); return 3
    if not isinstance(data, dict):
        issues.append({"severity": "blocker", "code": "contract_not_object"}); data = {}
    if data.get("schema") != "ai-ppt-plus/outline-contract/v1":
        issues.append({"severity": "blocker", "code": "contract_schema_invalid", "observed": data.get("schema")})
    for field in ("project_id", "outline_id", "outline_revision", "outline_path", "outline_sha256", "slide_count", "approval", "rows", "created_at"):
        if field not in data or data[field] in (None, "", []):
            issues.append({"severity": "blocker", "code": "contract_field_missing", "field": field})
    contract_outline = (path.parent / str(data.get("outline_path"))).resolve()
    if not contract_outline.is_file():
        issues.append({"severity": "blocker", "code": "outline_missing", "path": str(contract_outline)})
        rows = []
    else:
        observed_hash = sha256(contract_outline)
        if data.get("outline_sha256") != observed_hash:
            issues.append({"severity": "blocker", "code": "outline_hash_mismatch", "expected": data.get("outline_sha256"), "observed": observed_hash})
        try:
            rows = read_rows(contract_outline)
        except Exception as exc:
            rows = []
            issues.append({"severity": "blocker", "code": "outline_unreadable", "message": f"{type(exc).__name__}: {exc}"})
    if not SHA256_RE.fullmatch(str(data.get("outline_sha256") or "")):
        issues.append({"severity": "blocker", "code": "outline_hash_invalid"})
    if data.get("slide_count") != len(rows):
        issues.append({"severity": "blocker", "code": "slide_count_mismatch", "expected": data.get("slide_count"), "observed": len(rows)})
    contract_rows = {item.get("slide_no"): item for item in data.get("rows", []) if isinstance(item, dict)}
    for row in rows:
        try: slide_no = int(row.get("slide_no"))
        except (TypeError, ValueError): continue
        item = contract_rows.get(slide_no)
        if not item:
            issues.append({"severity": "blocker", "code": "contract_row_missing", "slide_no": slide_no}); continue
        if item.get("row_sha256") != row_digest(row):
            issues.append({"severity": "blocker", "code": "row_hash_mismatch", "slide_no": slide_no})
        if item.get("status") != str(row.get("status") or ""):
            issues.append({"severity": "blocker", "code": "row_status_mismatch", "slide_no": slide_no})
    if len(contract_rows) != len(rows):
        issues.append({"severity": "blocker", "code": "contract_row_count_mismatch", "expected": len(rows), "observed": len(contract_rows)})
    approval = data.get("approval") if isinstance(data.get("approval"), dict) else {}
    status = approval.get("status")
    if status not in STATES:
        issues.append({"severity": "blocker", "code": "approval_status_invalid", "status": status})
    if args.require_approved or status == "approved":
        if status != "approved": issues.append({"severity": "blocker", "code": "outline_not_approved", "status": status})
        if not approval.get("approved_by") or not approval.get("approved_at"):
            issues.append({"severity": "blocker", "code": "approval_evidence_missing"})
        for row in rows:
            if str(row.get("status") or "") not in {"approved", "superseded"}:
                issues.append({"severity": "blocker", "code": "approved_contract_contains_unapproved_row", "slide_no": row.get("slide_no")})
    for ref in data.get("source_references", []) or []:
        if not isinstance(ref, dict):
            issues.append({"severity": "blocker", "code": "source_reference_invalid"}); continue
        source = (path.parent / str(ref.get("path"))).resolve()
        if not source.is_file():
            issues.append({"severity": "blocker", "code": "source_reference_missing", "source_id": ref.get("source_id")})
        elif ref.get("sha256") and ref.get("sha256") != sha256(source):
            issues.append({"severity": "blocker", "code": "source_reference_hash_mismatch", "source_id": ref.get("source_id")})
    result = {"schema": "ai-ppt-plus/outline-contract-validation/v1", "valid": not issues, "contract": str(path), "project_id": data.get("project_id"), "outline_revision": data.get("outline_revision"), "outline_sha256": data.get("outline_sha256"), "slide_count": len(rows), "approval_status": status, "issues": issues}
    if args.report: atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
