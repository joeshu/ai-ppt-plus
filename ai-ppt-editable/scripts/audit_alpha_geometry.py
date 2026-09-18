#!/usr/bin/env python3
"""Audit transparent icon geometry against source Visual Lock targets."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from asset_placement import alpha_geometry


def _iou(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _center(box: list[float]) -> tuple[float, float]:
    return box[0] + box[2] / 2.0, box[1] + box[3] / 2.0


def _visible_box_on_slide(item: dict, geometry: dict) -> list[float]:
    canvas_w, canvas_h = geometry["canvas_px"]
    vx, vy, vw, vh = geometry["visible_bbox_px"]
    x, y, w, h = (float(item[k]) for k in ("x", "y", "w", "h"))
    return [x + w * vx / canvas_w, y + h * vy / canvas_h, w * vw / canvas_w, h * vh / canvas_h]


def audit(manifest: dict, assets_dir: Path) -> dict:
    rows = []
    for item in manifest.get("icons") or manifest.get("assets") or []:
        file = item.get("file")
        target = item.get("source_visible_bbox") or item.get("visual_lock_bbox")
        if not file or not target:
            continue
        path = Path(file); path = path if path.is_absolute() else assets_dir / path
        geometry = alpha_geometry(path, threshold=int(item.get("alpha_threshold", 8)))
        actual = _visible_box_on_slide(item, geometry)
        target = [float(v) for v in target]
        ac, tc = _center(actual), _center(target)
        diagonal = max(1e-9, math.hypot(target[2], target[3]))
        centroid_error = math.hypot(ac[0] - tc[0], ac[1] - tc[1]) / diagonal
        scale_error = max(abs(actual[2] / target[2] - 1.0), abs(actual[3] / target[3] - 1.0)) if target[2] > 0 and target[3] > 0 else 1.0
        bbox_iou = _iou(actual, target)
        passed = bbox_iou >= float(item.get("min_visible_iou", 0.85)) and centroid_error <= float(item.get("max_centroid_error", 0.08)) and scale_error <= float(item.get("max_scale_error", 0.15))
        rows.append({"object_id": item.get("object_id") or item.get("name") or file, "file": str(path), "alpha_geometry": geometry, "actual_visible_bbox": actual, "target_visible_bbox": target, "visible_bbox_iou": bbox_iou, "centroid_error_norm": centroid_error, "scale_error": scale_error, "valid": passed, "repair_trace": [] if passed else ["asset_geometry"]})
    failures = [row for row in rows if not row["valid"]]
    return {"schema": "ai-ppt-plus/alpha-geometry-qa/v1", "valid": not failures, "asset_count": len(rows), "failure_count": len(failures), "assets": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--assets-dir", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = audit(json.loads(args.manifest.read_text(encoding="utf-8")), args.assets_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "valid", "asset_count", "failure_count")}, ensure_ascii=False))
    return 0 if report["valid"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
