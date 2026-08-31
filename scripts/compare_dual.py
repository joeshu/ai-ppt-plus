#!/usr/bin/env python3
"""Unify pixel comparison and editable-object comparison evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/dual-comparison/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_json(path: Path, label: str, issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append({"severity": "blocker", "code": f"{label}_missing", "path": str(path)})
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append({"severity": "blocker", "code": f"{label}_unreadable", "message": str(exc)})
        return None
    if not isinstance(data, dict):
        issues.append({"severity": "blocker", "code": f"{label}_not_object"})
        return None
    return data


def manifest_summary(manifest: dict[str, Any] | None) -> dict[str, int]:
    expected = independent = formal_text = 0
    if manifest:
        for slide in manifest.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            objects = slide.get("objects")
            if not isinstance(objects, list):
                continue
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                expected += 1
                role = str(obj.get("role") or "").lower()
                if obj.get("independent") is True or obj.get("required_for_delivery") is True or role in {"icon", "brand_lockup", "semantic-panel", "product-image", "photo", "illustration"}:
                    independent += 1
                if obj.get("object_type") == "editable_text" or obj.get("contains_formal_content") is True:
                    formal_text += 1
    return {"expected_objects": expected, "expected_independent_objects": independent, "expected_formal_text_objects": formal_text}


def verify_file_binding(path_value: Any, hash_value: Any, label: str, issues: list[dict[str, Any]], *, required: bool) -> dict[str, Any]:
    evidence = {"path": path_value, "sha256": hash_value, "valid": False}
    if not isinstance(path_value, str) or not path_value.strip():
        if required:
            issues.append({"severity": "blocker", "code": f"{label}_path_missing"})
        return evidence
    path = Path(path_value).resolve()
    evidence["path"] = str(path)
    if not path.is_file():
        issues.append({"severity": "blocker", "code": f"{label}_file_missing", "path": str(path)})
        return evidence
    observed = digest(path)
    evidence["observed_sha256"] = observed
    if not isinstance(hash_value, str) or not SHA256_RE.fullmatch(hash_value):
        if required:
            issues.append({"severity": "blocker", "code": f"{label}_hash_missing", "path": str(path)})
        return evidence
    if hash_value != observed:
        issues.append({"severity": "blocker", "code": f"{label}_hash_mismatch", "path": str(path), "expected": observed, "observed": hash_value})
        return evidence
    evidence["valid"] = True
    return evidence


def pixel_bindings(visual: dict[str, Any] | None, issues: list[dict[str, Any]], *, required: bool) -> list[dict[str, Any]]:
    if not visual:
        return []
    pages = visual.get("pages")
    records: list[dict[str, Any]] = []
    if isinstance(pages, list) and pages:
        for page in pages:
            if not isinstance(page, dict):
                issues.append({"severity": "blocker", "code": "pixel_page_record_invalid"})
                continue
            slide = page.get("slide")
            records.append({
                "slide": slide,
                "rendered": verify_file_binding(page.get("rendered"), page.get("rendered_sha256"), "pixel_rendered", issues, required=required),
                "reference": verify_file_binding(page.get("reference"), page.get("reference_sha256"), "pixel_reference", issues, required=required),
            })
    elif visual.get("rendered") or visual.get("reference"):
        records.append({
            "slide": 1,
            "rendered": verify_file_binding(visual.get("rendered"), visual.get("rendered_sha256"), "pixel_rendered", issues, required=required),
            "reference": verify_file_binding(visual.get("reference"), visual.get("reference_sha256"), "pixel_reference", issues, required=required),
        })
    elif required:
        issues.append({"severity": "blocker", "code": "pixel_comparison_bindings_missing"})
    return records


def pixel_rollup(visual: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize both deck-level and single-page visual reports.

    ``compare_visual.py`` emits one page with top-level ``metrics`` while
    ``compare_visual_deck.py`` emits ``pages`` plus an ``aggregate`` object.
    Keep both forms equally informative in the unified report.
    """
    if not visual:
        return {"compared_pages": 0, "aggregate": {}, "metrics": {}, "page_metrics": []}

    pages = visual.get("pages")
    if isinstance(pages, list) and pages:
        aggregate = visual.get("aggregate") if isinstance(visual.get("aggregate"), dict) else {}
        page_metrics = [
            {"slide": page.get("slide"), "metrics": page.get("metrics", {})}
            for page in pages
            if isinstance(page, dict)
        ]
        compared_pages = aggregate.get("compared_pages")
        if not isinstance(compared_pages, int) or compared_pages < 0:
            compared_pages = sum(1 for item in page_metrics if item["metrics"]) or len(page_metrics)
        return {
            "compared_pages": compared_pages,
            "aggregate": aggregate,
            "metrics": {},
            "page_metrics": page_metrics,
        }

    metrics = visual.get("metrics") if isinstance(visual.get("metrics"), dict) else {}
    aggregate = visual.get("aggregate") if isinstance(visual.get("aggregate"), dict) else {}
    if not aggregate and metrics:
        blurred = metrics.get("blurred_layout_ssim")
        fidelity = metrics.get("pixel_fidelity_score")
        aggregate = {
            "compared_pages": 1,
            "worst_blurred_layout_ssim": blurred,
            "mean_blurred_layout_ssim": blurred,
            "mean_pixel_fidelity_score": fidelity,
        }
    return {
        "compared_pages": 1 if metrics else 0,
        "aggregate": aggregate,
        "metrics": metrics,
        "page_metrics": [],
    }


def build(visual_report_path: Path, output: Path, *, object_report_path: Path | None = None, object_manifest_path: Path | None = None, deck_path: Path | None = None, require_object: bool = False) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    visual = read_json(visual_report_path, "pixel_comparison", issues)
    if visual is not None and visual.get("valid") is not True:
        issues.append({"severity": "blocker", "code": "pixel_comparison_failed", "report_issues": visual.get("issues", [])})
    bindings = pixel_bindings(visual, issues, required=require_object)
    object_report = read_json(object_report_path, "object_comparison", issues) if object_report_path else None
    manifest = read_json(object_manifest_path, "object_manifest", issues) if object_manifest_path else None
    manifest_counts = manifest_summary(manifest)
    object_evidence: dict[str, Any]
    if object_report is None:
        object_evidence = {"status": "not-run", "valid": False, **manifest_counts}
        if require_object:
            issues.append({"severity": "blocker", "code": "object_comparison_required"})
    else:
        if object_report.get("valid") is not True:
            issues.append({"severity": "blocker", "code": "object_comparison_failed", "report_issues": object_report.get("errors", object_report.get("issues", []))})
        if require_object and (deck_path is None or not deck_path.is_file()):
            issues.append({"severity": "blocker", "code": "object_comparison_deck_required"})
        if require_object and (object_manifest_path is None or not object_manifest_path.is_file()):
            issues.append({"severity": "blocker", "code": "object_comparison_manifest_required"})
        if deck_path and deck_path.is_file():
            observed_deck_hash = digest(deck_path)
            declared_deck_hash = object_report.get("deck_sha256")
            if require_object and (not isinstance(declared_deck_hash, str) or not SHA256_RE.fullmatch(declared_deck_hash)):
                issues.append({"severity": "blocker", "code": "object_comparison_deck_hash_missing"})
            elif declared_deck_hash and declared_deck_hash != observed_deck_hash:
                issues.append({"severity": "blocker", "code": "object_comparison_stale_deck", "expected": observed_deck_hash, "observed": declared_deck_hash})
        if object_manifest_path and object_manifest_path.is_file():
            observed_manifest_hash = digest(object_manifest_path)
            declared_manifest_hash = object_report.get("object_manifest_sha256")
            if require_object and (not isinstance(declared_manifest_hash, str) or not SHA256_RE.fullmatch(declared_manifest_hash)):
                issues.append({"severity": "blocker", "code": "object_comparison_manifest_hash_missing"})
            elif declared_manifest_hash and declared_manifest_hash != observed_manifest_hash:
                issues.append({"severity": "blocker", "code": "object_comparison_stale_manifest", "expected": observed_manifest_hash, "observed": declared_manifest_hash})
        expected = manifest_counts["expected_objects"]
        audited = object_report.get("audited_object_count")
        if expected and audited != expected:
            issues.append({"severity": "blocker", "code": "object_comparison_count_mismatch", "expected": expected, "observed": audited})
        object_evidence = {
            "status": "passed" if object_report.get("valid") is True else "blocked",
            "valid": object_report.get("valid") is True,
            **manifest_counts,
            "audited_objects": audited,
            "observed_top_level_shapes": object_report.get("observed_top_level_shape_count"),
            "undeclared_shapes": object_report.get("undeclared_shape_count"),
            "object_manifest_sha256": object_report.get("object_manifest_sha256"),
            "errors": object_report.get("errors", []),
            "warnings": object_report.get("warnings", []),
        }
    pixel_rollup_data = pixel_rollup(visual)
    pixel_evidence = {
        "status": "passed" if visual and visual.get("valid") is True else "blocked",
        "valid": bool(visual and visual.get("valid") is True),
        "schema": visual.get("schema") if visual else None,
        "compared_pages": pixel_rollup_data["compared_pages"],
        "aggregate": pixel_rollup_data["aggregate"],
        "metrics": pixel_rollup_data["metrics"],
        "page_metrics": pixel_rollup_data["page_metrics"],
        "issues": visual.get("issues", []) if visual else [],
        "hash_bound": bool(bindings) and all(item["rendered"].get("valid") and item["reference"].get("valid") for item in bindings),
        "bindings": bindings,
    }
    result = {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "blocked" if issues else "passed" if object_evidence.get("valid") else "partial",
        "comparison_model": {
            "pixel": "reference-image-to-final-render",
            "object": "reference-derived-slide-object-manifest-to-final-pptx",
        },
        "pixel_comparison": pixel_evidence,
        "object_comparison": object_evidence,
        "issues": issues,
        "human_visual_review_required": True,
        "limitation": "pixel similarity does not prove editability; object similarity uses the approved semantic manifest rather than the flattened image object count",
    }
    if deck_path:
        result["deck"] = str(deck_path.resolve())
        result["deck_sha256"] = digest(deck_path) if deck_path.is_file() else None
    if object_manifest_path:
        result["object_manifest"] = str(object_manifest_path.resolve())
    atomic_write_json(output.resolve(), result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-report", required=True)
    parser.add_argument("--object-report")
    parser.add_argument("--object-manifest")
    parser.add_argument("--deck")
    parser.add_argument("--require-object", action="store_true")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        result = build(
            Path(args.visual_report).resolve(),
            Path(args.report).resolve(),
            object_report_path=Path(args.object_report).resolve() if args.object_report else None,
            object_manifest_path=Path(args.object_manifest).resolve() if args.object_manifest else None,
            deck_path=Path(args.deck).resolve() if args.deck else None,
            require_object=args.require_object,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": SCHEMA, "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "dual_comparison_failed", "message": str(exc)}]}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
