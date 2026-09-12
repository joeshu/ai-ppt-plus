#!/usr/bin/env python3
"""Validate semantic layout findings without hiding objects or widening tolerance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json


def bounds(item):
    position = item.get("position") or item.get("bbox") or item
    try: return [float(position[key]) for key in ("left", "top", "width", "height")]
    except (KeyError, TypeError, ValueError): return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    width = float(manifest.get("page_width", manifest.get("width", 1280)))
    height = float(manifest.get("page_height", manifest.get("height", 720)))
    findings, warnings = [], []
    objects = manifest.get("objects", [])
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            findings.append({"severity": "blocker", "code": "object_invalid", "index": index}); continue
        box = bounds(item)
        if box is None:
            findings.append({"severity": "blocker", "code": "object_bounds_missing", "index": index, "id": item.get("id")}); continue
        left, top, w, h = box
        if left < 0 or top < 0 or left + w > width or top + h > height:
            findings.append({"severity": "blocker", "code": "object_out_of_canvas", "index": index, "id": item.get("id"), "bbox": box, "canvas": [width, height]})
        for key, code in (("text_overflow", "text_overflow"), ("unexpected_line_break", "unexpected_line_break"), ("obscures_text", "object_obscures_text"), ("arrow_crosses_text", "arrow_crosses_text"), ("endpoint_offset", "connector_endpoint_offset"), ("border_missing", "table_border_missing")):
            if item.get(key): findings.append({"severity": "blocker", "code": code, "index": index, "id": item.get("id"), "evidence": item.get(key)})
    for index, table in enumerate(manifest.get("tables", [])):
        box = bounds(table)
        if box is None: findings.append({"severity": "blocker", "code": "table_bounds_missing", "index": index}); continue
        _, _, w, h = box
        cols = table.get("column_widths")
        rows = table.get("row_heights")
        if cols and abs(sum(float(v) for v in cols) - w) > 0.01:
            findings.append({"severity": "blocker", "code": "table_column_sum_mismatch", "index": index, "sum": sum(float(v) for v in cols), "width": w})
        if rows and abs(sum(float(v) for v in rows) - h) > 0.01:
            findings.append({"severity": "blocker", "code": "table_row_sum_mismatch", "index": index, "sum": sum(float(v) for v in rows), "height": h})
        if table.get("border_missing"): findings.append({"severity": "blocker", "code": "table_border_missing", "index": index})
    for index, overlay in enumerate(manifest.get("overlays", [])):
        if not overlay.get("target_cell") or not overlay.get("editable"):
            findings.append({"severity": "blocker", "code": "overlay_binding_missing", "index": index, "overlay": overlay})
        if overlay.get("alignment_after_reimport") is not True:
            findings.append({"severity": "blocker", "code": "overlay_alignment_unverified", "index": index})
    layers = [item for item in objects if isinstance(item, dict) and "z" in item]
    for item in layers:
        if item.get("layer_error"): findings.append({"severity": "blocker", "code": "layer_order_error", "id": item.get("id"), "evidence": item.get("layer_error")})
    result = {"schema": "ai-ppt-plus/layout-qa/v1", "valid": not findings,
              "status": "passed" if not findings else "blocked", "strict": args.strict,
              "canvas": {"width": width, "height": height}, "object_count": len(objects),
              "table_count": len(manifest.get("tables", [])), "overlay_count": len(manifest.get("overlays", [])),
              "findings": findings, "warnings": warnings,
              "rule": "Semantic findings are fixed in the owning geometry/object; tolerances, deletion and rasterization are not remediation."}
    atomic_write_json(Path(args.output).resolve(), result); print(json.dumps(result, ensure_ascii=False))
    return 0 if not findings else 2


if __name__ == "__main__": raise SystemExit(main())
