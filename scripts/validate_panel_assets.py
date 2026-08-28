#!/usr/bin/env python3
"""Validate independent assets for repeated reference-image panels."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from atomic_output import atomic_write_json

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional quality probe
    Image = None


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(2)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(path: str | None, result: dict) -> None:
    if path:
        out = Path(path)
        atomic_write_json(out.resolve(), result)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest")
    ap.add_argument("--require-independent", action="store_true")
    ap.add_argument("--expected-count", type=int, default=None)
    ap.add_argument("--assets-dir", default=None, help="Resolve panel files relative to this directory.")
    ap.add_argument("--require-approved", action="store_true", help="Require an explicit human approval record.")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()
    path = Path(args.manifest)
    if not path.exists():
        result = {"schema": "ai-ppt-plus/panel-assets-validation/v1", "valid": False, "status": "blocked", "errors": [f"manifest not found: {path}"], "warnings": []}
        write_report(args.report, result)
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/panel-assets-validation/v1", "valid": False, "status": "blocked", "errors": [f"invalid manifest: {type(exc).__name__}: {exc}"], "warnings": []}
        write_report(args.report, result)
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(2)
    panels = data.get("panels")
    errors: list[str] = []
    warnings: list[str] = []
    if args.require_approved or data.get("status") == "approved":
        if data.get("status") != "approved":
            errors.append("panel manifest must have status=approved")
        if not data.get("source_sha256"):
            errors.append("approved panel manifest must contain source_sha256")
        approval = data.get("approval")
        if not isinstance(approval, dict):
            errors.append("approved panel manifest must contain approval object")
        else:
            for field in ("reviewer", "approved_at", "revision", "candidate_manifest_sha256"):
                if not approval.get(field):
                    errors.append(f"approval.{field} is required")
    if not isinstance(panels, list):
        errors.append("manifest must contain panels[]")
        panels = []
    if args.expected_count is not None and len(panels) != args.expected_count:
        errors.append(f"expected {args.expected_count} panels, found {len(panels)}")
    ids, files = set(), set()
    assets_root = Path(args.assets_dir).resolve() if args.assets_dir else None
    source = Path(str(data.get("source"))).resolve() if data.get("source") else None
    if source and source.is_file() and data.get("source_sha256") and sha256(source) != data.get("source_sha256"):
        errors.append("source_sha256 does not match the current source image")
    source_size = data.get("source_size")
    if not (isinstance(source_size, list) and len(source_size) == 2 and all(isinstance(value, (int, float)) and value > 0 for value in source_size)):
        source_size = None
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
        asset_path = None
        if assets_root and file:
            asset_path = (assets_root / str(file)).resolve()
            try:
                asset_path.relative_to(assets_root)
            except ValueError:
                errors.append(f"panel {i} {pid}: asset path escapes assets-dir")
            if not asset_path.is_file():
                errors.append(f"panel {i} {pid}: asset not found: {asset_path}")
        if source_size and isinstance(panel.get("source_bbox"), list) and len(panel["source_bbox"]) == 4:
            x, y, w, h = panel["source_bbox"]
            if not all(isinstance(value, (int, float)) for value in (x, y, w, h)) or w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > source_size[0] or y + h > source_size[1]:
                errors.append(f"panel {i} {pid}: source_bbox is outside source_size")
        expected_size = panel.get("asset_size")
        if asset_path and asset_path.is_file() and Image and isinstance(expected_size, list) and len(expected_size) == 2:
            try:
                with Image.open(asset_path) as image:
                    if list(image.size) != expected_size:
                        errors.append(f"panel {i} {pid}: asset_size does not match decoded image size")
            except Exception as exc:
                errors.append(f"panel {i} {pid}: image decode failed: {type(exc).__name__}: {exc}")
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
        "status": "passed" if not errors else "blocked",
        "panel_count": len(panels),
        "errors": errors,
        "warnings": warnings,
        "human_visual_review_required": True,
    }
    write_report(args.report, result)
    print(json.dumps(result, ensure_ascii=False))
    if errors or (args.strict and warnings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
