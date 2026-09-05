#!/usr/bin/env python3
"""Validate that a delivered PPTX was authored in the current strict rerun.

This gate closes the manual-reuse loophole: a copied old PPTX (even with its old
provenance sidecar) cannot satisfy a newly-created run request because the
request_id, source/layout hashes and deck hash must all match.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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


def _check_file(record: dict, key: str, issues: list[dict]) -> None:
    item = record.get(key)
    if not isinstance(item, dict):
        issues.append({"code": f"{key}_evidence_missing"})
        return
    path_value = item.get("path")
    expected = item.get("sha256")
    if not isinstance(path_value, str) or not isinstance(expected, str):
        issues.append({"code": f"{key}_evidence_incomplete"})
        return
    path = Path(path_value)
    if not path.is_file():
        issues.append({"code": f"{key}_file_missing", "path": str(path)})
        return
    actual = sha256(path)
    if actual != expected:
        issues.append({"code": f"{key}_hash_mismatch", "expected": expected, "actual": actual})


def validate(request_path: Path, provenance_path: Path, deck_path: Path) -> dict:
    issues: list[dict] = []
    request = load(request_path)
    provenance = load(provenance_path)
    request_id = request.get("request_id")
    if not request_id or provenance.get("request_id") != request_id:
        issues.append({
            "code": "rerun_request_id_mismatch",
            "request_id": request_id,
            "provenance_request_id": provenance.get("request_id"),
        })
    if provenance.get("entrypoint") != "strict_reference_rerun.py":
        issues.append({"code": "nonstandard_authoring_entrypoint", "entrypoint": provenance.get("entrypoint")})
    if not deck_path.is_file():
        issues.append({"code": "deck_missing", "path": str(deck_path)})
    else:
        current_deck_hash = sha256(deck_path)
        if provenance.get("deck_sha256") != current_deck_hash:
            issues.append({
                "code": "stale_authoring_deck",
                "expected": provenance.get("deck_sha256"),
                "actual": current_deck_hash,
            })
    request_inputs = request.get("inputs") if isinstance(request.get("inputs"), dict) else {}
    provenance_inputs = provenance.get("inputs") if isinstance(provenance.get("inputs"), dict) else {}
    for key in ("source", "layout", "page_graph", "object_manifest", "imagegen_manifest"):
        req = request_inputs.get(key)
        prov = provenance_inputs.get(key)
        if req != prov:
            issues.append({"code": f"{key}_request_provenance_mismatch"})
        if isinstance(prov, dict):
            _check_file(provenance_inputs, key, issues)
    return {
        "schema": "ai-ppt-plus/authoring-provenance-validation/v1",
        "valid": not issues,
        "request_id": request_id,
        "deck": str(deck_path),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--deck", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        report = validate(Path(args.request), Path(args.provenance), Path(args.deck))
    except Exception as exc:
        report = {
            "schema": "ai-ppt-plus/authoring-provenance-validation/v1",
            "valid": False,
            "issues": [{"code": "authoring_provenance_unreadable", "message": f"{type(exc).__name__}: {exc}"}],
        }
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
