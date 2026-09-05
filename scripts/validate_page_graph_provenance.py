#!/usr/bin/env python3
"""Validate that PageGraph evidence belongs to the current reference rerun."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "ai-ppt-plus/page-graph-provenance-validation/v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def validate(provenance_path: Path, request_id: str, source_path: Path, page_graph_path: Path) -> dict:
    issues: list[dict] = []
    provenance = load(provenance_path)
    if provenance.get("schema") != "ai-ppt-plus/page-graph-provenance/v1":
        issues.append({"code": "page_graph_provenance_schema_invalid", "actual": provenance.get("schema")})
    if provenance.get("request_id") != request_id:
        issues.append({"code": "page_graph_request_id_mismatch", "expected": request_id, "actual": provenance.get("request_id")})
    producer = provenance.get("producer") if isinstance(provenance.get("producer"), dict) else {}
    if producer.get("task") != "visual-reconstruction":
        issues.append({"code": "page_graph_producer_task_invalid", "actual": producer.get("task")})
    for key, path in (("source", source_path), ("page_graph", page_graph_path)):
        evidence = provenance.get(key)
        if not isinstance(evidence, dict):
            issues.append({"code": f"{key}_evidence_missing"})
            continue
        if not path.is_file():
            issues.append({"code": f"{key}_file_missing", "path": str(path)})
            continue
        observed = sha256(path)
        if evidence.get("sha256") != observed:
            issues.append({"code": f"{key}_hash_mismatch", "expected": evidence.get("sha256"), "actual": observed})
    return {"schema": SCHEMA, "valid": not issues, "request_id": request_id, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--page-graph", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        report = validate(Path(args.provenance), args.request_id, Path(args.source), Path(args.page_graph))
    except Exception as exc:
        report = {"schema": SCHEMA, "valid": False, "request_id": args.request_id, "issues": [{"code": "page_graph_provenance_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
