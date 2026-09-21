#!/usr/bin/env python3
"""Validate evidence consistency for fixed-reference human visual closeout.

This gate intentionally does not impose an SSIM or pixel-score threshold.  It
blocks contradictory or incomplete closeout evidence: a page cannot be marked
passed while material crop findings or text-render repair items remain open.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_REGION_ROLES = {
    "brand",
    "title_typography",
    "primary_structure",
    "icons_or_complex_assets",
    "dense_or_repeated_content",
    "footer_or_edge_system",
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(closeout: dict[str, Any], local: dict[str, Any], text: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []

    def fail(code: str, message: str) -> None:
        issues.append({"severity": "blocker", "code": code, "message": message})

    if closeout.get("status") != "passed" or closeout.get("human_visual_review_status") != "passed":
        fail("human_visual_closeout_not_passed", "closeout and human visual review must both be passed")

    expected_reference = closeout.get("reference_sha256")
    expected_render = closeout.get("candidate_render_sha256")
    if not expected_reference or expected_reference != local.get("reference_sha256"):
        fail("closeout_reference_hash_mismatch", "closeout must bind the same immutable reference as local-crop evidence")
    if not expected_render or expected_render != local.get("candidate_sha256"):
        fail("closeout_render_hash_mismatch", "closeout must bind the exact final render used by local-crop evidence")

    regions = closeout.get("regions")
    if not isinstance(regions, list) or not regions:
        fail("structured_region_closeout_missing", "closeout regions must be a non-empty structured list")
        regions = []
    roles = {item.get("role") for item in regions if isinstance(item, dict)}
    missing_roles = sorted(REQUIRED_REGION_ROLES - roles)
    if missing_roles:
        fail("material_region_roles_missing", f"missing required region roles: {', '.join(missing_roles)}")

    local_ids = {item.get("region_id") for item in local.get("regions", []) if isinstance(item, dict)}
    for item in regions:
        if not isinstance(item, dict):
            fail("invalid_region_closeout", "every closeout region must be an object")
            continue
        region_id = item.get("region_id")
        if not region_id or region_id not in local_ids:
            fail("region_crop_evidence_missing", f"region {region_id or '?'} has no same-coordinate crop evidence")
        if item.get("status") != "passed":
            fail("material_visual_mismatch_open", f"region {region_id or '?'} is not passed")
        observation = item.get("observation")
        if not isinstance(observation, dict):
            fail("structured_observation_missing", f"region {region_id or '?'} lacks structured reference/candidate observation")
            continue
        for key in ("reference_features", "candidate_features", "mismatches"):
            if key not in observation:
                fail("structured_observation_incomplete", f"region {region_id or '?'} observation lacks {key}")
        mismatches = observation.get("mismatches")
        if not isinstance(mismatches, list):
            fail("invalid_mismatch_list", f"region {region_id or '?'} mismatches must be a list")
        elif mismatches:
            fail("material_visual_mismatch_open", f"region {region_id or '?'} still has {len(mismatches)} mismatch(es)")

    unresolved = closeout.get("unresolved_material_mismatches")
    if not isinstance(unresolved, list):
        fail("unresolved_mismatch_ledger_missing", "closeout must declare unresolved_material_mismatches as a list")
    elif unresolved:
        fail("material_visual_mismatch_open", f"{len(unresolved)} unresolved material visual mismatch(es) remain")

    repair_records = [r for r in text.get("records", []) if isinstance(r, dict) and r.get("repair_required") is True]
    dispositions = closeout.get("text_repair_dispositions")
    if not isinstance(dispositions, list):
        dispositions = []
    resolved = {
        item.get("object_id")
        for item in dispositions
        if isinstance(item, dict)
        and item.get("status") in {"resolved", "false_positive_verified"}
        and item.get("after_render_path")
        and item.get("review_note")
    }
    open_text = sorted({str(item.get("object_id")) for item in repair_records if item.get("object_id") not in resolved})
    if open_text:
        fail("text_render_repairs_unclosed", f"{len(open_text)} text-render repair item(s) lack resolved fresh-render disposition")

    text_candidate_hashes = {
        r.get("candidate", {}).get("render_sha256")
        for r in text.get("records", [])
        if isinstance(r, dict) and isinstance(r.get("candidate"), dict)
    }
    text_candidate_hashes.discard(None)
    if text_candidate_hashes and text_candidate_hashes != {expected_render}:
        fail("text_feedback_render_hash_mismatch", "text-render feedback is not bound exclusively to the final closeout render")

    return {
        "schema": "ai-ppt-plus/visual-closeout-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "failed",
        "reference_sha256": expected_reference,
        "candidate_render_sha256": expected_render,
        "region_count": len(regions),
        "open_text_repair_count": len(open_text),
        "issues": issues,
        "policy": "no scalar fidelity threshold; unresolved material findings and contradictory evidence block PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closeout", required=True, type=Path)
    parser.add_argument("--local-crop-report", required=True, type=Path)
    parser.add_argument("--text-render-feedback", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = validate(_load(args.closeout), _load(args.local_crop_report), _load(args.text_render_feedback))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
