#!/usr/bin/env python3
"""Audit B4/B5 frame-vs-icon layer evidence and assignments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def issue(items, severity, code, **extra):
    row = {"severity": severity, "code": code}
    row.update(extra)
    items.append(row)


def passed_review(value):
    return value == "pass" or (isinstance(value, dict) and value.get("status") == "pass")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--report")
    args = parser.parse_args()
    path = Path(args.manifest).resolve()
    issues, warnings = [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/icon-layer-audit/v1", "valid": False,
                  "status": "blocked", "issues": [{"severity": "blocker",
                  "code": "manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"}],
                  "warnings": []}
        if args.report:
            report = Path(args.report).resolve(); report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if not isinstance(data, dict) or data.get("schema") != "ai-ppt-plus/icon-assets/v1":
        issue(issues, "blocker", "schema_missing_or_invalid")
        data = {}
    assets = data.get("assets", [])
    if not isinstance(assets, list):
        issue(issues, "blocker", "assets_not_array")
        assets = []
    frame_ids = data.get("frame_asset_ids")
    icon_ids = data.get("icon_asset_ids")
    if not isinstance(frame_ids, list):
        issue(issues, "blocker", "frame_asset_ids_missing_or_invalid")
        frame_ids = []
    if not isinstance(icon_ids, list):
        issue(issues, "blocker", "icon_asset_ids_missing_or_invalid")
        icon_ids = []
    frame_set, icon_set = set(frame_ids), set(icon_ids)
    if len(frame_set) != len(frame_ids):
        issue(issues, "blocker", "duplicate_frame_asset_assignment")
    if len(icon_set) != len(icon_ids):
        issue(issues, "blocker", "duplicate_icon_asset_assignment")
    overlap = sorted(frame_set & icon_set)
    if overlap:
        issue(issues, "blocker", "duplicate_frame_icon_asset", asset_ids=overlap)
    known = {a.get("asset_id") for a in assets if isinstance(a, dict) and isinstance(a.get("asset_id"), str)}
    unknown_icons = sorted(icon_set - known)
    if unknown_icons:
        issue(issues, "blocker", "unknown_icon_asset_id", asset_ids=unknown_icons)
    unknown_frames = sorted(x for x in frame_set - known if x not in {"frame", "frame-layer"})
    if unknown_frames:
        issue(issues, "blocker", "unknown_frame_asset_id", asset_ids=unknown_frames)
    unassigned = sorted(known - frame_set - icon_set)
    if unassigned:
        issue(issues, "blocker", "unassigned_asset", asset_ids=unassigned)
    if not passed_review(data.get("source_vs_frame_review")):
        issue(issues, "blocker", "source_vs_frame_review_failed")
    for field in ("frame_preview", "contact_sheet"):
        value = data.get(field)
        if not isinstance(value, str) or not value:
            issue(issues, "blocker", "evidence_path_missing", field=field)
        elif not (path.parent / value).resolve().is_file():
            issue(issues, "blocker", "evidence_file_missing", field=field,
                  path=str((path.parent / value).resolve()))
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            continue
        if asset.get("asset_id") in icon_set:
            exclusion = asset.get("frame_exclusion")
            if exclusion not in {"verified-not-in-frame", "verified", "pass"} and not (
                isinstance(exclusion, dict) and exclusion.get("status") == "pass"
            ):
                issue(issues, "blocker", "icon_frame_exclusion_unverified", asset_index=index,
                      asset_id=asset.get("asset_id"))
    result = {
        "schema": "ai-ppt-plus/icon-layer-audit/v1",
        "valid": not any(x["severity"] == "blocker" for x in issues),
        "status": "passed" if not issues else "blocked",
        "manifest": str(path),
        "asset_count": len(assets),
        "frame_asset_ids": sorted(frame_set),
        "icon_asset_ids": sorted(icon_set),
        "issues": issues,
        "warnings": warnings,
        "human_visual_review_required": True,
    }
    if args.report:
        report = Path(args.report).resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
