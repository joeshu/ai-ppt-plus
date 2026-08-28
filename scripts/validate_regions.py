#!/usr/bin/env python3
"""Validate arbitrary-count rectangular or polygonal semantic regions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def polygon_area(points: list[list[float]]) -> float:
    return abs(sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points))) / 2.0)


def validate(data: dict[str, Any]) -> dict[str, Any]:
    canvas = data.get("canvas") or data.get("source_size")
    if isinstance(canvas, dict):
        width, height = canvas.get("width"), canvas.get("height")
    elif isinstance(canvas, list) and len(canvas) == 2:
        width, height = canvas
    else:
        width = height = None
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)) or width <= 0 or height <= 0:
        issues.append({"severity": "blocker", "code": "canvas_invalid"})
        width = height = 0
    regions = data.get("regions")
    if regions is None:
        regions = data.get("panels")
    if not isinstance(regions, list) or not regions:
        issues.append({"severity": "blocker", "code": "regions_missing"})
        regions = []
    seen: set[str] = set()
    normalized = []
    for index, region in enumerate(regions):
        path = f"regions[{index}]"
        if not isinstance(region, dict):
            issues.append({"severity": "blocker", "code": "region_not_object", "path": path})
            continue
        region_id = str(region.get("region_id") or region.get("panel_id") or region.get("id") or "").strip()
        if not region_id:
            issues.append({"severity": "blocker", "code": "region_id_missing", "path": path})
        elif region_id in seen:
            issues.append({"severity": "blocker", "code": "region_id_duplicate", "region_id": region_id})
        seen.add(region_id)
        polygon = region.get("polygon")
        bbox = region.get("bbox") or region.get("source_bbox")
        points: list[list[float]] | None = None
        if polygon is not None:
            if not isinstance(polygon, list) or len(polygon) < 3:
                issues.append({"severity": "blocker", "code": "polygon_invalid", "region_id": region_id})
            else:
                try:
                    points = [[float(point[0]), float(point[1])] for point in polygon]
                except (TypeError, ValueError, IndexError):
                    issues.append({"severity": "blocker", "code": "polygon_coordinates_invalid", "region_id": region_id})
                if points:
                    if polygon_area(points) <= 0:
                        issues.append({"severity": "blocker", "code": "polygon_zero_area", "region_id": region_id})
                    if any(x < 0 or y < 0 or x > width or y > height for x, y in points):
                        issues.append({"severity": "blocker", "code": "polygon_out_of_bounds", "region_id": region_id})
                    bbox = [min(point[0] for point in points), min(point[1] for point in points), max(point[0] for point in points) - min(point[0] for point in points), max(point[1] for point in points) - min(point[1] for point in points)]
        if bbox is not None:
            if not isinstance(bbox, list) or len(bbox) != 4:
                issues.append({"severity": "blocker", "code": "bbox_invalid", "region_id": region_id})
            else:
                try:
                    x, y, w, h = (float(value) for value in bbox)
                except (TypeError, ValueError):
                    x = y = w = h = 0
                    issues.append({"severity": "blocker", "code": "bbox_coordinates_invalid", "region_id": region_id})
                if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
                    issues.append({"severity": "blocker", "code": "bbox_out_of_bounds", "region_id": region_id})
        elif points is None:
            issues.append({"severity": "blocker", "code": "region_geometry_missing", "region_id": region_id})
        normalized.append({"region_id": region_id, "geometry": "polygon" if points else "bbox", "bbox": bbox, "polygon": points, "object_id": region.get("object_id"), "independent": region.get("independent", True)})

    result = {
        "schema": "ai-ppt-plus/region-validation/v1",
        "valid": not any(issue.get("severity") == "blocker" for issue in issues),
        "status": "passed" if not issues else "blocked",
        "canvas": [width, height],
        "region_count": len(regions),
        "regions": normalized,
        "issues": issues,
        "warnings": warnings,
        "human_visual_review_required": True,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        result = validate(data if isinstance(data, dict) else {})
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/region-validation/v1", "valid": False, "status": "invalid", "issues": [{"severity": "blocker", "code": "manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"}], "warnings": []}
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
