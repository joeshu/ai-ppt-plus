#!/usr/bin/env python3
"""Enforce the image-to-editable-PPT raster/text boundary."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from atomic_output import atomic_write_json


ALLOWED_AUDIT_STATUS = {"verified-clear", "verified-excluded", "brand-lockup-exempt"}
RASTER_TYPES = {"independent_image", "traceable_static_graphic", "extracted_icon"}
BLOCKED_TYPES = {"flattened_full_slide", "whole_slide_image", "screenshot"}


def read(path: Path | None) -> dict:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def issue(issues: list[dict], code: str, message: str, **extra: object) -> None:
    issues.append({"severity": "blocker", "code": code, "message": message, **extra})


def audit_record(value: object, *, path: str, issues: list[dict]) -> dict | None:
    if not isinstance(value, dict):
        issue(issues, "raster_text_audit_missing", f"{path} requires raster_text_audit", path=path)
        return None
    status = value.get("status")
    if status not in ALLOWED_AUDIT_STATUS:
        issue(issues, "raster_text_audit_status_invalid", f"{path} has no approved text audit status", path=path, observed=status)
        return None
    if not isinstance(value.get("method"), str) or not value["method"].strip():
        issue(issues, "raster_text_audit_method_missing", f"{path} requires a non-empty audit method", path=path)
    if not isinstance(value.get("reviewed_at"), str) or not value["reviewed_at"].strip():
        issue(issues, "raster_text_audit_time_missing", f"{path} requires reviewed_at", path=path)
    ids = value.get("text_layer_ids")
    if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
        issue(issues, "raster_text_layer_ids_invalid", f"{path} requires text_layer_ids[]", path=path)
        ids = []
    if status == "verified-clear" and ids:
        issue(issues, "clear_raster_has_text_layers", f"{path} is verified-clear but lists native text layers", path=path)
    if status == "verified-excluded" and not ids:
        issue(issues, "excluded_raster_has_no_text_layers", f"{path} is verified-excluded but has no native text layer IDs", path=path)
    return {"status": status, "text_layer_ids": ids}


def ratio(layout: dict) -> float | None:
    width, height = layout.get("slide_width_in"), layout.get("slide_height_in")
    if not (isinstance(width, (int, float)) and isinstance(height, (int, float)) and width > 0 and height > 0):
        width, height = layout.get("ref_width"), layout.get("ref_height")
    if isinstance(width, (int, float)) and isinstance(height, (int, float)) and width > 0 and height > 0:
        return float(width) / float(height)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", required=True)
    parser.add_argument("--object-manifest", required=True)
    parser.add_argument("--panel-manifest")
    parser.add_argument("--report", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    issues: list[dict] = []
    warnings: list[dict] = []
    layout_path = Path(args.layout).resolve()
    object_path = Path(args.object_manifest).resolve()
    panel_path = Path(args.panel_manifest).resolve() if args.panel_manifest else None
    for path, label in ((layout_path, "layout"), (object_path, "object_manifest")):
        if not path.is_file():
            issue(issues, f"{label}_missing", f"{label} is required for strict image-to-editable validation", path=str(path))
    if issues:
        result = {"schema": "ai-ppt-plus/image-to-editable-contract-validation/v1", "valid": False, "status": "blocked", "issues": issues, "warnings": warnings}
        atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 1

    try:
        layout = read(layout_path)
        objects_manifest = read(object_path)
        panel_manifest = read(panel_path) if panel_path else {}
    except Exception as exc:
        issue(issues, "manifest_unreadable", f"unable to read contract manifests: {type(exc).__name__}: {exc}")
        layout, objects_manifest, panel_manifest = {}, {}, {}

    observed_ratio = ratio(layout)
    if observed_ratio is None:
        issue(issues, "slide_ratio_missing", "layout must declare slide dimensions or ref_width/ref_height")
    elif abs(observed_ratio - (16 / 9)) > 0.02:
        warnings.append({"code": "source_ratio_preserved", "message": "reference is not 16:9; preserve the source ratio and document it"})

    slides = objects_manifest.get("slides")
    if not isinstance(slides, list) or not slides:
        issue(issues, "object_manifest_slides_missing", "object manifest must contain slides[]")
        slides = []
    formal_ids: set[str] = set()
    raster_objects: list[dict] = []
    for slide_no, slide in enumerate(slides, 1):
        for obj in slide.get("objects", []) if isinstance(slide, dict) else []:
            if not isinstance(obj, dict):
                continue
            object_id = str(obj.get("object_id", f"slide-{slide_no}-object"))
            object_type = obj.get("object_type")
            if object_type == "editable_text" or obj.get("role") == "formal-text":
                if object_type != "editable_text":
                    issue(issues, "formal_text_not_editable", f"{object_id} is formal text but not editable_text", object_id=object_id)
                text_spec = obj.get("text_spec")
                if not isinstance(text_spec, dict) or not str(text_spec.get("content", "")).strip():
                    issue(issues, "formal_text_content_missing", f"{object_id} has no editable text content", object_id=object_id)
                formal_ids.add(object_id)
            if object_type in BLOCKED_TYPES or obj.get("role") == "flattened_full_slide":
                issue(issues, "flattened_full_slide_forbidden", f"{object_id} is a forbidden flattened slide object", object_id=object_id)
            if object_type in RASTER_TYPES:
                raster_objects.append(obj)
                if obj.get("contains_formal_content") is True:
                    issue(issues, "formal_content_rasterized", f"{object_id} declares formal content in a raster asset", object_id=object_id)
                if obj.get("asset_policy") == "brand_lockup":
                    if obj.get("raster_text_audit", {}).get("status") == "brand-lockup-exempt":
                        continue
                audit_record(obj.get("raster_text_audit"), path=f"object:{object_id}", issues=issues)
    if not formal_ids:
        issue(issues, "formal_text_objects_missing", "reference reconstruction must produce at least one native formal text object")

    panel_ids: set[str] = set()
    panel_audits: dict[str, dict] = {}
    panels = panel_manifest.get("panels") if isinstance(panel_manifest, dict) else None
    if panels is not None:
        if not isinstance(panels, list):
            issue(issues, "panel_manifest_invalid", "panel manifest panels must be a list")
        else:
            for index, panel in enumerate(panels, 1):
                if not isinstance(panel, dict):
                    issue(issues, "panel_record_invalid", f"panel {index} is not an object")
                    continue
                panel_id = str(panel.get("panel_id", ""))
                panel_ids.add(panel_id)
                if panel.get("formal_text_baked_in") is not False:
                    issue(issues, "formal_text_baked_in", f"panel {panel_id or index} must explicitly exclude formal text", panel_id=panel_id)
                audit = audit_record(panel.get("raster_text_audit"), path=f"panel:{panel_id or index}", issues=issues)
                if audit is not None:
                    panel_audits[panel_id] = audit
                    for text_id in audit["text_layer_ids"]:
                        if text_id not in formal_ids:
                            issue(issues, "text_layer_unresolved", f"panel {panel_id} points to missing native text object {text_id}", panel_id=panel_id, text_layer_id=text_id)
    elif raster_objects:
        issue(issues, "panel_manifest_missing", "raster panels require panel-asset-manifest.json with text audit evidence")

    for obj in raster_objects:
        if obj.get("role") == "semantic-panel" and panel_ids and str(obj.get("object_id")) not in panel_ids:
            issue(issues, "panel_object_unregistered", f"semantic panel {obj.get('object_id')} is missing from panel manifest", object_id=obj.get("object_id"))
        audit = obj.get("raster_text_audit")
        if isinstance(audit, dict):
            for text_id in audit.get("text_layer_ids", []):
                if text_id not in formal_ids:
                    issue(issues, "text_layer_unresolved", f"object {obj.get('object_id')} points to missing native text object {text_id}", object_id=obj.get("object_id"), text_layer_id=text_id)

    if not args.strict and issues:
        warnings.extend(issues)
        issues = []
    result = {
        "schema": "ai-ppt-plus/image-to-editable-contract-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "strict": args.strict,
        "observed_ratio": observed_ratio,
        "formal_text_object_count": len(formal_ids),
        "raster_object_count": len(raster_objects),
        "panel_count": len(panel_ids),
        "issues": issues,
        "warnings": warnings,
        "human_visual_review_required": True,
    }
    atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
