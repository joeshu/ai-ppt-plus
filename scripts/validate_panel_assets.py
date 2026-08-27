#!/usr/bin/env python3
"""Validate independent assets for repeated reference-image panels."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest")
    ap.add_argument("--require-independent", action="store_true")
    ap.add_argument("--expected-count", type=int, default=None)
    ap.add_argument("--assets-dir", default=None, help="Resolve panel files relative to this directory.")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()
    path = Path(args.manifest)
    if not path.exists():
        die(f"manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    panels = data.get("panels")
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(panels, list):
        errors.append("manifest must contain panels[]")
        panels = []
    if args.expected_count is not None and len(panels) != args.expected_count:
        errors.append(f"expected {args.expected_count} panels, found {len(panels)}")
    ids, files = set(), set()
    for i, panel in enumerate(panels, 1):
        if not isinstance(panel, dict):
            errors.append(f"panel {i} is not an object")
            continue
        pid, file = panel.get("panel_id"), panel.get("file")
        if not pid or pid in ids:
            errors.append(f"panel {i}: missing or duplicate panel_id")
        ids.add(pid)
        if not file or file in files:
            errors.append(f"panel {i}: missing or duplicate independent file")
        files.add(file)
        if args.assets_dir and file and not (Path(args.assets_dir) / str(file)).exists():
            errors.append(f"panel {i} {pid}: asset not found: {Path(args.assets_dir) / str(file)}")
        if not isinstance(panel.get("source_bbox"), list) or len(panel["source_bbox"]) != 4:
            warnings.append(f"panel {i} {pid}: missing source_bbox")
        if panel.get("treatment") not in {"native-shape", "transparent-image", "vector"}:
            warnings.append(f"panel {i} {pid}: treatment should be native-shape, transparent-image or vector")
        if panel.get("formal_text_baked_in"):
            errors.append(f"panel {i} {pid}: formal text is baked into panel asset")
    if args.require_independent and data.get("whole_frame"):
        errors.append("whole_frame is present in independent-panel mode")
    result = {
        "schema": "ai-ppt-plus/panel-assets-validation/v1",
        "valid": not errors,
        "panel_count": len(panels),
        "errors": errors,
        "warnings": warnings,
        "human_visual_review_required": True,
    }
    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if errors or (args.strict and warnings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
