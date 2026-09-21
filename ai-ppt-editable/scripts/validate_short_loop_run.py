#!/usr/bin/env python3
"""Validate the self-contained fixed-reference reconstruction loop.

This validator deliberately blocks only deterministic correctness failures.
Visual metrics are retained as diagnostics and can create repair work, but they
cannot fail acceptance by themselves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
sys.path.insert(0, str(Path(__file__).resolve().parent))
from execution_profiles import PROFILES

PHASES = [
    "reference",
    "execution_preflight",
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
    profile_name = str(report.get("execution_profile") or "fast").lower()
    policy = PROFILES.get(profile_name)
    if policy is None or not policy["delivery_allowed"]:
        fail(errors, f"invalid delivery execution profile: {profile_name}")
        policy = PROFILES["fast"]

    for phase in PHASES:
        if not phase_done(report, phase):
            fail(errors, f"required phase incomplete: {phase}")

    preflight = report.get("preflight")
    if not isinstance(preflight, dict) or preflight.get("valid") is not True:
        fail(errors, "execution preflight missing or blocked")
    else:
        required_checks = ("package", "source", "runtime", "font", "finalizer")
        checks = preflight.get("checks") if isinstance(preflight.get("checks"), dict) else {}
        for name in required_checks:
            if checks.get(name) != "passed":
                fail(errors, f"execution preflight check not passed: {name}")

    performance = report.get("performance")
    if not isinstance(performance, dict):
        fail(errors, "performance budget missing")
    else:
        try:
            repair_rounds = max(0, int(performance.get("repair_rounds", 0)))
            max_repair_rounds = max(0, int(performance.get("max_repair_rounds", policy["repair_round_limit"])))
            candidate_builds = max(0, int(performance.get("candidate_build_count", 0)))
            full_renders = max(0, int(performance.get("full_render_count", 0)))
        except (TypeError, ValueError):
            fail(errors, "performance counts must be integers")
            repair_rounds = max_repair_rounds = candidate_builds = full_renders = 0
        if max_repair_rounds != policy["repair_round_limit"]:
            fail(errors, "declared repair budget differs from execution profile")
        if repair_rounds > max_repair_rounds and not performance.get("budget_exception_reason"):
            fail(errors, f"repair-round budget exceeded: {repair_rounds} > {max_repair_rounds}")
        if candidate_builds > policy["candidate_limit"]:
            fail(errors, f"candidate-build budget exceeded: {candidate_builds} > {policy['candidate_limit']}")
        if full_renders > policy["full_render_limit"]:
            fail(errors, f"full-render budget exceeded: {full_renders} > {policy['full_render_limit']}")
        for asset_id, count in (performance.get("imagegen_retry_counts") or {}).items():
            if int(count) > policy["imagegen_retry_limit_per_asset"]:
                fail(errors, f"ImageGen retry budget exceeded for {asset_id}: {count} > {policy['imagegen_retry_limit_per_asset']}")
        if performance.get("text_fit_scope") != policy["text_fit_scope"]:
            fail(errors, "text-fit scope differs from execution profile")
        if performance.get("authoritative_visual_renderer") != "libreoffice+poppler":
            fail(errors, "authoritative visual renderer must be libreoffice+poppler")
        if performance.get("artifact_tool_preview_used_for_visual_closeout") is True:
            fail(errors, "Artifact Tool preview cannot be visual-closeout authority")

    benchmark = report.get("benchmark")
    required_benchmark = (
        "ttfvr_seconds", "wall_time_seconds", "candidate_count", "full_render_count",
        "imagegen_call_count", "native_text_coverage", "required_native_coverage",
        "whole_slide_raster_count", "material_mismatch_count",
        "protected_regression_count", "reproducible",
    )
    if not isinstance(benchmark, dict):
        fail(errors, "benchmark evidence missing")
    else:
        for key in required_benchmark:
            if key not in benchmark:
                fail(errors, f"benchmark metric missing: {key}")
        for key in ("ttfvr_seconds", "wall_time_seconds", "candidate_count", "full_render_count", "imagegen_call_count", "whole_slide_raster_count", "material_mismatch_count", "protected_regression_count"):
            if key in benchmark and (not isinstance(benchmark[key], (int, float)) or benchmark[key] < 0):
                fail(errors, f"benchmark metric invalid: {key}")
        for key in ("native_text_coverage", "required_native_coverage"):
            if key in benchmark and (not isinstance(benchmark[key], (int, float)) or not 0 <= benchmark[key] <= 1):
                fail(errors, f"benchmark ratio invalid: {key}")
        if benchmark.get("required_native_coverage") != 1:
            fail(errors, "required native coverage must equal 1.0")
        if benchmark.get("whole_slide_raster_count") != 0:
            fail(errors, "whole-slide raster count must equal zero")
        if benchmark.get("protected_regression_count") != 0:
            fail(errors, "protected regression count must equal zero")
        if benchmark.get("reproducible") is not True:
            fail(errors, "run is not reproducible")

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
        minimum = min(policy["local_crop_min"], material_regions) if material_regions > 0 else 0
        if len(crops) < minimum:
            fail(errors, f"page {page_id}: only {len(crops)} local crops; need >= {minimum}")
        if len(crops) > policy["local_crop_max"]:
            fail(errors, f"page {page_id}: {len(crops)} local crops exceed profile maximum {policy['local_crop_max']}")
        render_sha = final.get("render_sha256")
        for crop in crops:
            if not crop.get("reference_path") or not crop.get("candidate_path"):
                fail(errors, f"page {page_id}: crop missing same-coordinate evidence")
            if crop.get("same_coordinates") is not True:
                fail(errors, f"page {page_id}: crop is not marked same_coordinates=true")
            if crop.get("source_render_sha256") != render_sha:
                fail(errors, f"page {page_id}: crop was not cut from the final full-page render")

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
