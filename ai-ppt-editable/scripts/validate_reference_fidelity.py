#!/usr/bin/env python3
"""Validate object-family evidence for reference reconstruction fidelity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMA = "ai-ppt-plus/reference-fidelity/v1"
ICON_MODES = {"source_reuse", "imagegen"}
GRADIENT_TREATMENTS = {"native_gradient", "source_asset", "bounded_degradation"}


def issue(issues: list[dict], code: str, **extra: object) -> None:
    issues.append({"severity": "blocker", "code": code, **extra})


def bbox_ok(value: object) -> bool:
    return isinstance(value, list) and len(value) == 4 and all(isinstance(x, (int, float)) for x in value)


def hash_ok(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--report")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    issues: list[dict] = []
    try:
        data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except Exception as exc:
        data = {}
        issue(issues, "invalid_manifest", message=str(exc))

    if data.get("schema") != SCHEMA:
        issue(issues, "schema_mismatch", expected=SCHEMA)
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else {}
    for name, record in (("source", source), ("candidate", candidate)):
        if not record.get("path"):
            issue(issues, f"{name}_path_missing")
        size = record.get("size")
        if not (isinstance(size, list) and len(size) == 2 and all(isinstance(x, (int, float)) and x > 0 for x in size)):
            issue(issues, f"{name}_size_invalid")
    policy = data.get("aspect_ratio_policy")
    if source.get("size") and candidate.get("size"):
        source_ratio = float(source["size"][0]) / float(source["size"][1])
        candidate_ratio = float(candidate["size"][0]) / float(candidate["size"][1])
        if abs(source_ratio - candidate_ratio) > 0.01:
            override = data.get("aspect_ratio_override")
            if not isinstance(override, dict) or not override.get("approved") or not override.get("mapping"):
                issue(issues, "silent_aspect_ratio_change", source_ratio=source_ratio, candidate_ratio=candidate_ratio)
    if policy not in {"preserve-source", "declared-fit", "declared-crop"}:
        issue(issues, "aspect_ratio_policy_missing")

    icons = data.get("icons") if isinstance(data.get("icons"), list) else []
    for item in icons:
        ident = item.get("semantic_id")
        if not ident:
            issue(issues, "icon_id_missing")
        if not bbox_ok(item.get("source_bbox")):
            issue(issues, "icon_source_bbox_missing", semantic_id=ident)
        if item.get("provenance_mode") not in ICON_MODES:
            issue(issues, "icon_provenance_missing", semantic_id=ident)
        if item.get("placeholder") is True or item.get("fallback_symbol"):
            issue(issues, "icon_placeholder_or_symbol", semantic_id=ident)
        if not hash_ok(item.get("asset_sha256")):
            issue(issues, "icon_asset_hash_missing", semantic_id=ident)
        if not item.get("pptx_object_ids") or not item.get("render_bbox"):
            issue(issues, "icon_object_or_render_evidence_missing", semantic_id=ident)
        if item.get("visual_status") != "pass":
            issue(issues, "icon_visual_status_not_pass", semantic_id=ident)

    texts = data.get("text_regions") if isinstance(data.get("text_regions"), list) else []
    for item in texts:
        ident = item.get("text_id")
        if not ident or not isinstance(item.get("text"), str) or not item.get("text"):
            issue(issues, "text_content_missing", text_id=ident)
        if not bbox_ok(item.get("source_bbox")):
            issue(issues, "text_source_bbox_missing", text_id=ident)
        if not item.get("pptx_object_ids"):
            issue(issues, "text_native_object_missing", text_id=ident)
        if not isinstance(item.get("runs"), list) or not item["runs"]:
            issue(issues, "text_style_runs_missing", text_id=ident)
        if item.get("visual_status") != "pass":
            issue(issues, "text_visual_status_not_pass", text_id=ident)

    gradients = data.get("gradient_regions") if isinstance(data.get("gradient_regions"), list) else []
    for item in gradients:
        ident = item.get("gradient_id")
        treatment = item.get("treatment")
        if not ident or not bbox_ok(item.get("source_bbox")):
            issue(issues, "gradient_identity_or_bbox_missing", gradient_id=ident)
        if treatment not in GRADIENT_TREATMENTS:
            issue(issues, "gradient_treatment_missing", gradient_id=ident)
        if treatment == "native_gradient":
            stops = item.get("stops")
            if not isinstance(stops, list) or len(stops) < 2:
                issue(issues, "native_gradient_stops_missing", gradient_id=ident)
        elif treatment == "source_asset":
            if not hash_ok(item.get("asset_sha256")) or not item.get("asset_path"):
                issue(issues, "gradient_asset_provenance_missing", gradient_id=ident)
        elif treatment == "bounded_degradation" and not item.get("degradation_reason"):
            issue(issues, "gradient_degradation_reason_missing", gradient_id=ident)
        if item.get("render_visible") is not True:
            issue(issues, "gradient_render_visibility_missing", gradient_id=ident)
        if item.get("source_nonuniform") is True and treatment == "flat_fill":
            issue(issues, "gradient_silently_flattened", gradient_id=ident)

    if args.strict and not icons:
        issue(issues, "icon_roster_empty")
    if args.strict and not texts:
        issue(issues, "text_roster_empty")
    if args.strict and not gradients:
        issue(issues, "gradient_roster_empty")
    report = {"schema": "ai-ppt-plus/reference-fidelity-validation/v1", "valid": not issues, "status": "passed" if not issues else "blocked", "icons": len(icons), "text_regions": len(texts), "gradient_regions": len(gradients), "issues": issues}
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
