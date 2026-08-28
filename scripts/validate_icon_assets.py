#!/usr/bin/env python3
"""Validate an icon/decorative asset roster and extracted image files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from atomic_output import atomic_write_json

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

ROLES = {"icon", "decoration", "badge", "logo", "illustration", "decorative_word_art", "frame_exclusion"}
METHODS = {"approved-source-asset", "image-generation", "native-vector", "chroma-cutout", "contact-sheet-split", "placeholder"}
LEVELS = {"L1", "L2", "L4", "L5"}


def add(issues, severity, code, index=None, **extra):
    item = {"severity": severity, "code": code}
    if index is not None:
        item["asset_index"] = index
    item.update(extra)
    issues.append(item)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--report")
    args = parser.parse_args()
    manifest_path = Path(args.manifest).resolve()
    issues, warnings = [], []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/icon-assets-validation/v1", "valid": False, "status": "invalid", "issues": [{"severity": "blocker", "code": "manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"}], "warnings": []}
        if args.report:
            report = Path(args.report).resolve(); atomic_write_json(report, result)
        print(json.dumps(result, ensure_ascii=False)); return 2
    if not isinstance(data, dict) or data.get("schema") != "ai-ppt-plus/icon-assets/v1":
        add(issues, "blocker", "schema_missing_or_invalid", expected="ai-ppt-plus/icon-assets/v1")
        assets = []
    else:
        assets = data.get("assets", [])
    if not isinstance(assets, list):
        add(issues, "blocker", "assets_not_array"); assets = []
    # B4/B5 evidence is project-level, not optional metadata.
    top_required = ("source_vs_frame_review", "frame_asset_ids", "icon_asset_ids", "frame_preview", "contact_sheet")
    for field in top_required:
        if field not in data or data[field] in (None, ""):
            add(issues, "blocker", "top_level_evidence_missing", field=field)
    review = data.get("source_vs_frame_review")
    review_pass = review == "pass" or (isinstance(review, dict) and review.get("status") == "pass")
    if not review_pass:
        add(issues, "blocker", "source_vs_frame_review_failed")
    for field in ("frame_asset_ids", "icon_asset_ids"):
        if field in data and not isinstance(data[field], list):
            add(issues, "blocker", "top_level_id_list_invalid", field=field)
    for field in ("frame_preview", "contact_sheet"):
        value = data.get(field)
        if isinstance(value, str) and value:
            evidence_path = (manifest_path.parent / value).resolve()
            if not evidence_path.is_file():
                add(issues, "blocker", "evidence_file_missing", field=field, path=str(evidence_path))
    seen = set()
    required = ("role", "source_ref", "source_bbox", "extraction_method", "frame_exclusion", "editability_level", "asset_path", "alpha_quality", "edge_touch", "split_status", "duplicate_guard", "anchor", "review_status")
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            add(issues, "blocker", "asset_not_object", index); continue
        asset_id = asset.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip(): add(issues, "blocker", "asset_id_missing", index)
        elif asset_id in seen: add(issues, "blocker", "asset_id_duplicate", index, asset_id=asset_id)
        else: seen.add(asset_id)
        for field in required:
            if field not in asset or asset[field] in (None, ""): add(issues, "blocker", "required_field_missing", index, field=field)
        if asset.get("role") not in ROLES: add(issues, "blocker", "invalid_role", index, value=asset.get("role"))
        if asset.get("extraction_method") not in METHODS: add(issues, "blocker", "invalid_extraction_method", index, value=asset.get("extraction_method"))
        if asset.get("editability_level") not in LEVELS: add(issues, "blocker", "invalid_editability_level", index, value=asset.get("editability_level"))
        bbox = asset.get("source_bbox")
        valid_bbox = isinstance(bbox, dict) and all(isinstance(bbox.get(k), (int, float)) and bbox.get(k) >= 0 for k in ("x", "y", "w", "h")) and bbox.get("w", 0) > 0 and bbox.get("h", 0) > 0
        if not valid_bbox: add(issues, "blocker", "invalid_source_bbox", index)
        if asset.get("edge_touch") is True and asset.get("edge_touch_accepted") is not True: add(issues, "blocker", "unexpected_edge_touch", index)
        if asset.get("alpha_quality") not in {"pass", "not-applicable"}: add(issues, "blocker", "alpha_quality_failed", index, value=asset.get("alpha_quality"))
        if asset.get("duplicate_guard") != "pass": add(issues, "blocker", "duplicate_guard_failed", index)
        if asset.get("editability_level") == "L2" and asset.get("replaceable") is not True: add(issues, "blocker", "l2_not_replaceable", index)
        if asset.get("editability_level") == "L5": add(issues, "blocker", "unresolved_asset", index)
        if asset.get("extraction_method") == "image-generation" and not isinstance(asset.get("prompt_ref"), str): add(issues, "blocker", "generation_evidence_missing", index)
        if asset.get("extraction_method") in {"chroma-cutout", "contact-sheet-split"} and not isinstance(asset.get("cutout_method"), str): add(issues, "blocker", "cutout_evidence_missing", index)
        asset_path = asset.get("asset_path")
        native_ref = isinstance(asset_path, str) and asset_path.startswith("native:")
        if isinstance(asset_path, str) and asset_path and not native_ref and asset.get("extraction_method") != "placeholder":
            path = (manifest_path.parent / asset_path).resolve()
            if not path.is_file(): add(issues, "blocker", "asset_file_missing", index, path=str(path))
            elif Image is not None:
                try:
                    with Image.open(path) as image:
                        if image.width <= 0 or image.height <= 0: add(issues, "blocker", "asset_empty", index, path=str(path))
                        if "A" in image.getbands() and image.getchannel("A").getbbox() is None: add(issues, "blocker", "asset_alpha_empty", index, path=str(path))
                except Exception as exc: add(issues, "blocker", "asset_unreadable", index, message=f"{type(exc).__name__}: {exc}")
            else: warnings.append({"severity": "major", "code": "pillow_unavailable_for_alpha_check", "asset_index": index})
    result = {"schema": "ai-ppt-plus/icon-assets-validation/v1", "valid": not any(x.get("severity") == "blocker" for x in issues), "status": "passed" if not issues else "blocked", "manifest": str(manifest_path), "asset_count": len(assets), "issues": issues, "warnings": warnings, "human_visual_review_required": True}
    if args.report:
        report = Path(args.report).resolve(); atomic_write_json(report, result)
    print(json.dumps(result, ensure_ascii=False)); return 0 if result["valid"] else 2


if __name__ == "__main__": raise SystemExit(main())
