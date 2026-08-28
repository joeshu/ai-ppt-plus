#!/usr/bin/env python3
"""Validate the canonical semantic inventory for an editable deck."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from atomic_output import atomic_write_json
from editability import validate_objects, summarize_objects


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest")
    ap.add_argument("--expected-pages", type=int, help="require contiguous slide coverage for this many pages")
    ap.add_argument("--require-panels", action="store_true")
    ap.add_argument("--expected-panel-count", type=int)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()
    path = Path(args.manifest)
    errors, warnings = [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("manifest must be an object")
    except Exception as exc:
        errors.append({"code": "invalid_json", "message": f"{type(exc).__name__}: {exc}"})
        data = {}
    if data.get("schema") != "ai-ppt-plus/slide-object-manifest/v1":
        errors.append({"code": "schema_invalid", "message": "expected slide-object-manifest/v1"})
    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append({"code": "slides_missing", "message": "slides[] is required"})
        slides = []
    slide_numbers = []
    for index, slide in enumerate(slides, 1):
        if not isinstance(slide, dict):
            continue
        try:
            slide_numbers.append(int(slide.get("slide_no", index)))
        except (TypeError, ValueError):
            errors.append({"code": "invalid_slide_number", "slide": index})
    if len(slide_numbers) != len(set(slide_numbers)):
        errors.append({"code": "duplicate_slide_number"})
    expected_numbers = list(range(1, (args.expected_pages if args.expected_pages is not None else len(slides)) + 1))
    if sorted(slide_numbers) != expected_numbers:
        errors.append({"code": "slide_coverage_not_contiguous", "expected": expected_numbers, "observed": sorted(slide_numbers)})
    seen_global = set()
    panel_ids = []
    slide_summaries = []
    for si, slide in enumerate(slides, 1):
        objects = slide.get("objects") if isinstance(slide, dict) else None
        if not isinstance(objects, list):
            errors.append({"code": "objects_missing", "slide": si, "message": "slide.objects[] is required"})
            objects = []
        issues = validate_objects(objects)
        for issue in issues:
            issue["slide"] = si
            errors.append(issue)
        local = set()
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            oid = obj.get("object_id")
            if oid in local:
                errors.append({"code": "duplicate_object_id", "slide": si, "object_id": oid})
            local.add(oid)
            if oid in seen_global:
                errors.append({"code": "duplicate_object_id_global", "object_id": oid})
            seen_global.add(oid)
            if obj.get("role") in {"semantic-panel", "panel", "frame-panel"}:
                panel_ids.append(oid)
                if obj.get("independent") is not True:
                    errors.append({"code": "panel_not_independent", "slide": si, "object_id": oid})
            if obj.get("role") == "formal-text" and obj.get("object_type") != "editable_text":
                errors.append({"code": "formal_text_not_editable", "slide": si, "object_id": oid})
        slide_summaries.append({"slide": si, **summarize_objects(objects), "issues": issues})
    if args.require_panels and not panel_ids:
        errors.append({"code": "panels_missing", "message": "at least one semantic panel is required"})
    if args.expected_panel_count is not None and len(panel_ids) != args.expected_panel_count:
        errors.append({"code": "panel_count_mismatch", "expected": args.expected_panel_count, "observed": len(panel_ids)})
    result = {"schema": "ai-ppt-plus/slide-object-manifest-validation/v1", "valid": not errors and not (args.strict and warnings), "manifest": str(path.resolve()), "slides": slide_summaries, "panel_ids": panel_ids, "component_usage": data.get("component_usage", {"instances": 0, "distinct_components": 0, "by_component": {}, "reused_component_types": 0}), "errors": errors, "warnings": warnings, "human_visual_review_required": True}
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
