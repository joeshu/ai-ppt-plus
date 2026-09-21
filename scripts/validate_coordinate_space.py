#!/usr/bin/env python3
"""Validate one declared coordinate space across an editable layout."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

SCHEMA = "ai-ppt-plus/coordinate-space-validation/v1"
UNITS = {"fraction", "normalized", "px", "pt", "in"}
SPACE = {
    "fraction": "normalized",
    "normalized": "normalized",
    "px": "reference_pixels",
    "pt": "slide_points",
    "in": "slide_inches",
}
KINDS = ("texts", "shapes", "tables", "charts", "icons", "images", "connectors", "groups", "objects")


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _bbox(spec: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = spec.get("bbox")
    values = raw if isinstance(raw, (list, tuple)) and len(raw) == 4 else [spec.get(key) for key in ("x", "y", "w", "h")]
    if len(values) != 4:
        return None
    parsed = tuple(_number(value) for value in values)
    if any(value is None for value in parsed):
        return None
    return parsed  # type: ignore[return-value]


def _canvas(deck: dict[str, Any], units: str) -> tuple[float, float] | None:
    if units in {"fraction", "normalized"}:
        return 1.0, 1.0
    if units == "px":
        width = deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px")
        height = deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px")
    elif units == "pt":
        width = deck.get("slide_width_pt")
        height = deck.get("slide_height_pt")
        if width is None and deck.get("slide_width_in") is not None:
            width = _number(deck.get("slide_width_in"))
            width = width * 72 if width is not None else None
        if height is None and deck.get("slide_height_in") is not None:
            height = _number(deck.get("slide_height_in"))
            height = height * 72 if height is not None else None
    else:
        width = deck.get("slide_width_in")
        height = deck.get("slide_height_in")
    parsed = (_number(width), _number(height))
    if parsed[0] is None or parsed[1] is None or parsed[0] <= 0 or parsed[1] <= 0:
        return None
    return parsed  # type: ignore[return-value]


def _object_id(spec: dict[str, Any], kind: str, index: int) -> str:
    return str(spec.get("object_id") or spec.get("id") or spec.get("name") or f"{kind}-{index}")


def validate(deck: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    units = deck.get("units", "fraction")
    if units not in UNITS:
        return {"schema": SCHEMA, "valid": False, "status": "blocked", "coordinate_space": units, "canvas": None, "object_count": 0, "issues": [{"severity": "blocker", "code": "coordinate_units_invalid", "observed": units}]}
    expected_space = SPACE[units]
    declared_space = deck.get("coordinate_space")
    if declared_space is not None and declared_space != expected_space:
        issues.append({"severity": "blocker", "code": "coordinate_space_mismatch", "expected": expected_space, "observed": declared_space})
    canvas = _canvas(deck, units)
    if canvas is None:
        issues.append({"severity": "blocker", "code": "coordinate_canvas_missing", "units": units})
        canvas = (0.0, 0.0)
    width, height = canvas
    object_count = 0
    for slide_index, slide in enumerate(deck.get("slides") or [], 1):
        if not isinstance(slide, dict):
            issues.append({"severity": "blocker", "code": "coordinate_slide_invalid", "slide": slide_index})
            continue
        for kind in KINDS:
            values = slide.get(kind) or []
            if not isinstance(values, list):
                issues.append({"severity": "blocker", "code": "coordinate_object_list_invalid", "slide": slide_index, "kind": kind})
                continue
            for index, spec in enumerate(values, 1):
                if not isinstance(spec, dict):
                    issues.append({"severity": "blocker", "code": "coordinate_object_invalid", "slide": slide_index, "kind": kind, "index": index})
                    continue
                object_count += 1
                object_id = _object_id(spec, kind, index)
                object_space = spec.get("coordinate_space") or spec.get("bbox_units")
                if object_space is not None and object_space != expected_space:
                    issues.append({"severity": "blocker", "code": "object_coordinate_space_mismatch", "slide": slide_index, "kind": kind, "object_id": object_id, "expected": expected_space, "observed": object_space})
                box = _bbox(spec)
                if box is None:
                    issues.append({"severity": "blocker", "code": "object_bbox_missing_or_invalid", "slide": slide_index, "kind": kind, "object_id": object_id})
                    continue
                x, y, w, h = box
                line_like = str(spec.get("type") or "").lower() in {"line", "connector", "curve"}
                if x < 0 or y < 0 or w < 0 or h < 0 or (w == 0 and h == 0) or (not line_like and (w <= 0 or h <= 0)):
                    issues.append({"severity": "blocker", "code": "object_bbox_non_positive", "slide": slide_index, "kind": kind, "object_id": object_id, "bbox": list(box)})
                    continue
                if x + w > width + 1e-6 or y + h > height + 1e-6:
                    issues.append({"severity": "blocker", "code": "object_out_of_canvas", "slide": slide_index, "kind": kind, "object_id": object_id, "bbox": list(box), "canvas": [width, height]})
                if isinstance(spec.get("bbox"), list) and any(_number(item) is None for item in spec["bbox"]):
                    issues.append({"severity": "blocker", "code": "object_bbox_non_numeric", "slide": slide_index, "kind": kind, "object_id": object_id})
    return {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "coordinate_space": expected_space,
        "units": units,
        "canvas": {"width": width, "height": height},
        "object_count": object_count,
        "issues": issues,
        "human_visual_review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.layout.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("layout must contain a JSON object")
        result = validate(value)
    except Exception as exc:
        result = {"schema": SCHEMA, "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "coordinate_layout_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
