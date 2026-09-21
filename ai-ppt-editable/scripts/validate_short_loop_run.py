#!/usr/bin/env python3
"""Validate the Knight-style short reconstruction loop.

This validator deliberately blocks only deterministic correctness failures.
Visual metrics are retained as diagnostics and can create repair work, but they
cannot fail acceptance by themselves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PHASES = [
    "reference",
    "visual_inventory",
    "classification",
    "text_slot_preflight",
    "asset_generation",
    "artifact_tool_build",
    "fresh_powerpoint_render",
    "full_page_compare",
    "local_crop_qa",
    "responsible_object_repair",
    "rerender",
    "visual_closeout_consistency",
    "hard_correctness_check",
    "final_pptx",
]

HARD_BLOCKERS = {
    "corrupt_or_unrenderable",
    "formal_text_loss",
    "whole_slide_raster_fallback",
    "required_editability_loss",
    "asset_missing_or_invalid_alpha",
    "severe_overflow_collision_oob",
    "semantic_table_misclassification",
    "chart_blank_serialized_as_zero",
    "source_or_provenance_mismatch",
}

DIAGNOSTIC_KEYS = {
    "ssim",
    "regional_ssim",
    "pixel_score",
    "five_dim_score",
    "bbox_iou",
    "centroid_drift",
    "scale_drift",
    "icon_similarity",
    "text_fit_utilization",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def phase_done(report: dict[str, Any], phase: str) -> bool:
    value = report.get("phases", {}).get(phase)
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return value.get("status") in {"done", "passed", "complete", "completed"}
    return False


def validate(report: dict[str, Any], root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for phase in PHASES:
        if not phase_done(report, phase):
            fail(errors, f"required phase incomplete: {phase}")

    source = report.get("source", {})
    source_path = root / source.get("path", "")
    expected_source_sha = source.get("sha256")
    if not source_path.is_file():
        fail(errors, f"source missing: {source_path}")
    elif not expected_source_sha or sha256(source_path) != expected_source_sha:
        fail(errors, "source_or_provenance_mismatch: source SHA-256 mismatch")

    final = report.get("final", {})
    pptx_path = root / final.get("pptx_path", "")
    render_path = root / final.get("render_path", "")
    if not pptx_path.is_file():
        fail(errors, f"final PPTX missing: {pptx_path}")
    elif final.get("pptx_sha256") and sha256(pptx_path) != final["pptx_sha256"]:
        fail(errors, "source_or_provenance_mismatch: final PPTX SHA-256 mismatch")
    if not render_path.is_file():
        fail(errors, f"fresh render missing: {render_path}")
    elif final.get("render_sha256") and sha256(render_path) != final["render_sha256"]:
        fail(errors, "source_or_provenance_mismatch: final render SHA-256 mismatch")

    blockers = report.get("hard_blockers", [])
    for item in blockers:
        category = item.get("category") if isinstance(item, dict) else str(item)
        active = item.get("active", True) if isinstance(item, dict) else True
        if category not in HARD_BLOCKERS:
            fail(errors, f"invalid hard-blocker category: {category}")
        elif active:
            fail(errors, f"active hard blocker: {category}")

    # Guard against accidentally turning diagnostics into blockers.
    for key in report.get("blocking_metrics", {}):
        if key in DIAGNOSTIC_KEYS:
            fail(errors, f"diagnostic metric illegally configured as production blocker: {key}")

    pages = report.get("pages", [])
    if not pages:
        fail(errors, "no page records")
    for page in pages:
        page_id = page.get("page_id", "?")
        crops = page.get("local_crops", [])
        material_regions = int(page.get("material_region_count", len(crops)))
        minimum = min(5, material_regions) if material_regions > 0 else 0
        if len(crops) < minimum:
            fail(errors, f"page {page_id}: only {len(crops)} local crops; need >= {minimum}")
        if len(crops) > 10:
            warnings.append(f"page {page_id}: {len(crops)} final crops; contract targets 5-10")
        for crop in crops:
            if not crop.get("reference_path") or not crop.get("candidate_path"):
                fail(errors, f"page {page_id}: crop missing same-coordinate evidence")
            if crop.get("same_coordinates") is not True:
                fail(errors, f"page {page_id}: crop is not marked same_coordinates=true")

    repairs = report.get("repair_trace", [])
    for item in repairs:
        if not item.get("responsible_object_id") and not item.get("responsible_layer"):
            fail(errors, "repair item missing responsible object/layer")
        if item.get("accepted") is True and not item.get("after_render_path"):
            fail(errors, "accepted repair missing fresh after-render evidence")

    closeout = report.get("visual_closeout_validation")
    if not isinstance(closeout, dict):
        fail(errors, "visual closeout validation missing")
    elif closeout.get("valid") is not True or closeout.get("status") != "passed":
        fail(errors, "visual closeout consistency failed")
    elif int(closeout.get("open_text_repair_count", 0)) != 0:
        fail(errors, "visual closeout has open text-render repairs")

    metrics = report.get("diagnostics", {})
    for key in metrics:
        if key not in DIAGNOSTIC_KEYS:
            warnings.append(f"unclassified diagnostic metric retained as non-blocking: {key}")

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    errors, warnings = validate(report, args.root)
    result = {
        "ok": not errors,
        "hard_blocker_policy": sorted(HARD_BLOCKERS),
        "errors": errors,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASSED" if result["ok"] else "FAILED")
        for error in errors:
            print(f"ERROR: {error}")
        for warning in warnings:
            print(f"WARN: {warning}")
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
