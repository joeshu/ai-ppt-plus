#!/usr/bin/env python3
"""Fail closed when native table text collides with overlay assets or cannot fit."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from atomic_output import atomic_write_json


def _box(item: dict) -> tuple[float, float, float, float]:
    return tuple(float(item.get(key, 0)) for key in ("x", "y", "w", "h"))


def _intersection(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0.0, min(ay + ah, by + bh) - max(ay, by))


def _parts(values, count: int, total: float) -> list[float]:
    if isinstance(values, list) and len(values) >= count:
        parts = [float(value) for value in values[:count]]
        scale = total / sum(parts) if sum(parts) > 0 else 0
        return [value * scale for value in parts]
    return [total / count] * count


def validate(deck: dict) -> dict:
    issues: list[dict] = []
    if deck.get("units", "fraction") != "fraction":
        issues.append({"severity": "blocker", "code": "table_layout_units_unsupported"})
        return {"schema": "ai-ppt-plus/table-layout-validation/v1", "valid": False, "issues": issues}
    slide_width_pt = float(deck.get("slide_width_in", 13.333)) * 72
    slide_height_pt = float(deck.get("slide_height_in", 7.5)) * 72
    for slide_index, slide in enumerate(deck.get("slides", []), 1):
        assets = [item for key in ("icons", "images") for item in slide.get(key, []) if isinstance(item, dict)]
        for table_index, table in enumerate(slide.get("tables", []), 1):
            rows = table.get("rows") or []
            columns = int(table.get("columns") or (len(rows[0]) if rows else 0))
            if not rows or columns <= 0:
                continue
            tx, ty, tw, th = _box(table)
            col_widths = _parts(table.get("column_widths"), columns, tw)
            row_heights = _parts(table.get("row_heights"), len(rows), th)
            default_margins = table.get("cell_margins") or table.get("padding") or {}
            styles = table.get("cell_styles") or {}
            cy = ty
            for row_index, (row, row_height) in enumerate(zip(rows, row_heights)):
                cx = tx
                for column_index, column_width in enumerate(col_widths):
                    style = styles.get(f"{row_index},{column_index}", styles.get(str(row_index), {})) if isinstance(styles, dict) else {}
                    style = style if isinstance(style, dict) else {}
                    margins = style.get("margins", default_margins) or {}
                    # Margin values are points in the authoring contract.
                    left = float(margins.get("left", 0)) / slide_width_pt
                    right = float(margins.get("right", 0)) / slide_width_pt
                    top = float(margins.get("top", 0)) / slide_height_pt
                    bottom = float(margins.get("bottom", 0)) / slide_height_pt
                    safe = (cx + left, cy + top, max(0, column_width - left - right), max(0, row_height - top - bottom))
                    cell_id = f"{table.get('object_id') or f'table-{table_index}'}:{row_index},{column_index}"
                    value = row[column_index] if column_index < len(row) else ""
                    text = str(value.get("text", "") if isinstance(value, dict) else (value or ""))
                    for asset in assets if text else []:
                        overlap = _intersection(safe, _box(asset))
                        if overlap > 1e-9:
                            issues.append({
                                "severity": "blocker", "code": "table_cell_asset_text_collision",
                                "slide": slide_index, "cell_id": cell_id,
                                "asset_id": asset.get("object_id") or asset.get("name"),
                                "intersection_area": round(overlap, 9),
                            })
                    size = float(style.get("size", table.get("size", deck.get("theme", {}).get("size", 12))))
                    line_height = size * float(style.get("line_spacing", table.get("line_spacing", 1.2))) / slide_height_pt
                    cjk_units = sum(1.0 if ord(char) > 255 else 0.55 for char in text)
                    chars_per_line = max(1.0, safe[2] * slide_width_pt / max(size, 1.0))
                    needed_lines = max(1, math.ceil(cjk_units / chars_per_line)) if text else 0
                    if needed_lines * line_height > safe[3] + 1e-9:
                        issues.append({
                            "severity": "blocker", "code": "table_cell_capacity_exceeded",
                            "slide": slide_index, "cell_id": cell_id,
                            "needed_lines": needed_lines, "available_height": round(safe[3], 6),
                        })
                    cx += column_width
                cy += row_height
    return {"schema": "ai-ppt-plus/table-layout-validation/v1", "valid": not issues, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck")
    parser.add_argument("--report")
    args = parser.parse_args()
    result = validate(json.loads(Path(args.deck).read_text(encoding="utf-8")))
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
