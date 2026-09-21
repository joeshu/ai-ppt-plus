#!/usr/bin/env python3
"""Fail closed when native table text collides with overlay assets or cannot fit."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from atomic_output import atomic_write_json


UNITS = {"fraction", "normalized", "px", "pt", "in"}


def _number(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _canvas(deck: dict, units: str) -> tuple[float, float, float, float] | None:
    slide_width_in = _number(deck.get("slide_width_in")) or 13.333
    slide_height_in = _number(deck.get("slide_height_in")) or 7.5
    slide_width_pt = slide_width_in * 72
    slide_height_pt = slide_height_in * 72
    if units in {"fraction", "normalized"}:
        return 1.0, 1.0, slide_width_pt, slide_height_pt
    if units == "px":
        width = deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px")
        height = deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px")
    elif units == "pt":
        width = deck.get("slide_width_pt") or slide_width_pt
        height = deck.get("slide_height_pt") or slide_height_pt
    else:
        width = deck.get("slide_width_in")
        height = deck.get("slide_height_in")
    width_number = _number(width)
    height_number = _number(height)
    if width_number is None or height_number is None or width_number <= 0 or height_number <= 0:
        return None
    return width_number, height_number, slide_width_pt, slide_height_pt


def _box(item: dict) -> tuple[float, float, float, float] | None:
    raw = item.get("bbox")
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        values = raw
    else:
        values = [item.get(key) for key in ("x", "y", "w", "h")]
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in result):
        return None
    return result


def _intersection(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0.0, min(ay + ah, by + bh) - max(ay, by))


def _parts(values, count: int, total: float) -> list[float]:
    if count <= 0:
        return []
    if isinstance(values, (list, tuple)) and len(values) >= count:
        try:
            parts = [float(value) for value in values[:count]]
        except (TypeError, ValueError):
            return [0.0] * count
        total_parts = sum(parts)
        scale = total / total_parts if total_parts > 0 else 0
        return [value * scale for value in parts]
    return [total / count] * count


def _table_id(table: dict, index: int) -> str:
    return str(table.get("object_id") or table.get("id") or f"table-{index}")


def validate(deck: dict) -> dict:
    issues: list[dict] = []
    units = str(deck.get("units", "fraction")).strip().lower()
    if units not in UNITS:
        issues.append({"severity": "blocker", "code": "table_layout_units_unsupported", "observed": units})
        return {"schema": "ai-ppt-plus/table-layout-validation/v2", "valid": False, "status": "blocked", "coordinate_space": units, "issues": issues, "density_metrics": [], "human_visual_review_required": True}
    canvas = _canvas(deck, units)
    if canvas is None:
        issues.append({"severity": "blocker", "code": "table_layout_canvas_missing", "units": units})
        return {"schema": "ai-ppt-plus/table-layout-validation/v2", "valid": False, "status": "blocked", "coordinate_space": units, "issues": issues, "density_metrics": [], "human_visual_review_required": True}
    canvas_width, canvas_height, slide_width_pt, slide_height_pt = canvas
    scale_x = slide_width_pt / canvas_width
    scale_y = slide_height_pt / canvas_height
    density_metrics: list[dict] = []
    slides = deck.get("slides", [])
    if not isinstance(slides, list):
        issues.append({"severity": "blocker", "code": "table_layout_slides_invalid"})
        slides = []
    theme = deck.get("theme") if isinstance(deck.get("theme"), dict) else {}
    for slide_index, slide in enumerate(slides, 1):
        if not isinstance(slide, dict):
            issues.append({"severity": "blocker", "code": "table_layout_slide_invalid", "slide": slide_index})
            continue
        assets: list[dict] = []
        for key in ("icons", "images"):
            values = slide.get(key, []) or []
            if not isinstance(values, list):
                issues.append({"severity": "blocker", "code": "table_overlay_asset_list_invalid", "slide": slide_index, "kind": key})
                continue
            assets.extend(item for item in values if isinstance(item, dict))
        tables = slide.get("tables", []) or []
        if not isinstance(tables, list):
            issues.append({"severity": "blocker", "code": "table_list_invalid", "slide": slide_index})
            continue
        for table_index, table in enumerate(tables, 1):
            if not isinstance(table, dict):
                issues.append({"severity": "blocker", "code": "table_record_invalid", "slide": slide_index, "table_index": table_index})
                continue
            table_id = _table_id(table, table_index)
            rows = table.get("rows")
            if not isinstance(rows, list) or not rows:
                issues.append({"severity": "blocker", "code": "table_rows_missing", "slide": slide_index, "table_id": table_id})
                continue
            raw_columns = table.get("columns")
            if raw_columns is None:
                first_row = rows[0] if isinstance(rows[0], list) else []
                raw_columns = len(first_row)
            try:
                raw_columns_number = float(raw_columns)
                columns = int(raw_columns_number)
                if not math.isfinite(raw_columns_number) or columns != raw_columns_number:
                    raise ValueError
            except (TypeError, ValueError):
                columns = 0
            if columns <= 0:
                issues.append({"severity": "blocker", "code": "table_columns_invalid", "slide": slide_index, "table_id": table_id, "columns": raw_columns})
                continue
            table_box = _box(table)
            if table_box is None:
                issues.append({"severity": "blocker", "code": "table_bbox_invalid", "slide": slide_index, "table_id": table_id})
                continue
            tx, ty, tw, th = table_box
            if tx < 0 or ty < 0 or tw <= 0 or th <= 0 or tx + tw > canvas_width + 1e-6 or ty + th > canvas_height + 1e-6:
                issues.append({"severity": "blocker", "code": "table_bbox_out_of_canvas", "slide": slide_index, "table_id": table_id, "bbox": list(table_box), "canvas": [canvas_width, canvas_height]})
                continue
            longest_row = max((len(row) for row in rows if isinstance(row, list)), default=0)
            if longest_row > columns:
                issues.append({"severity": "blocker", "code": "table_row_column_count_exceeded", "slide": slide_index, "table_id": table_id, "columns": columns, "longest_row": longest_row})
            col_widths = _parts(table.get("column_widths"), columns, tw)
            row_heights = _parts(table.get("row_heights"), len(rows), th)
            if any(value <= 0 for value in col_widths):
                issues.append({"severity": "blocker", "code": "table_column_width_invalid", "slide": slide_index, "table_id": table_id, "column_widths": col_widths})
            if any(value <= 0 for value in row_heights):
                issues.append({"severity": "blocker", "code": "table_row_height_invalid", "slide": slide_index, "table_id": table_id, "row_heights": row_heights})
            default_margins = table.get("cell_margins") or table.get("padding") or {}
            if not isinstance(default_margins, dict):
                issues.append({"severity": "blocker", "code": "table_cell_margins_invalid", "slide": slide_index, "table_id": table_id})
                default_margins = {}
            styles = table.get("cell_styles") or {}
            if not isinstance(styles, dict):
                issues.append({"severity": "blocker", "code": "table_cell_styles_invalid", "slide": slide_index, "table_id": table_id})
                styles = {}
            cy = ty
            for row_index, (row, row_height) in enumerate(zip(rows, row_heights)):
                if not isinstance(row, list):
                    issues.append({"severity": "blocker", "code": "table_row_invalid", "slide": slide_index, "table_id": table_id, "row": row_index})
                    row = []
                cx = tx
                for column_index, column_width in enumerate(col_widths):
                    style = styles.get(f"{row_index},{column_index}", styles.get(str(row_index), {}))
                    style = style if isinstance(style, dict) else {}
                    margins = style.get("margins", default_margins) or {}
                    if not isinstance(margins, dict):
                        issues.append({"severity": "blocker", "code": "table_cell_margins_invalid", "slide": slide_index, "cell_id": f"{table_id}:{row_index},{column_index}"})
                        margins = {}
                    margin_values = {}
                    for margin_name in ("left", "right", "top", "bottom"):
                        parsed_margin = _number(margins.get(margin_name, 0))
                        if parsed_margin is None or parsed_margin < 0:
                            issues.append({"severity": "blocker", "code": "table_cell_margin_invalid", "slide": slide_index, "cell_id": f"{table_id}:{row_index},{column_index}", "margin": margin_name})
                            parsed_margin = 0.0
                        margin_values[margin_name] = parsed_margin
                    # Margins are points; cell coordinates follow the declared layout units.
                    left = margin_values["left"] / slide_width_pt * canvas_width
                    right = margin_values["right"] / slide_width_pt * canvas_width
                    top = margin_values["top"] / slide_height_pt * canvas_height
                    bottom = margin_values["bottom"] / slide_height_pt * canvas_height
                    safe = (cx + left, cy + top, max(0, column_width - left - right), max(0, row_height - top - bottom))
                    safe_pt = (safe[0] * scale_x, safe[1] * scale_y, safe[2] * scale_x, safe[3] * scale_y)
                    cell_id = f"{table_id}:{row_index},{column_index}"
                    value = row[column_index] if column_index < len(row) else ""
                    text = str(value.get("text", "") if isinstance(value, dict) else (value or ""))
                    if safe_pt[2] <= 0 or safe_pt[3] <= 0:
                        issues.append({"severity": "blocker", "code": "table_cell_usable_box_empty", "slide": slide_index, "cell_id": cell_id, "usable_box_pt": [round(value, 6) for value in safe_pt]})
                    for asset in assets if text else []:
                        asset_box_raw = _box(asset)
                        if asset_box_raw is None:
                            issues.append({"severity": "blocker", "code": "table_overlay_asset_bbox_invalid", "slide": slide_index, "cell_id": cell_id, "asset_id": asset.get("object_id") or asset.get("name")})
                            continue
                        asset_box = (asset_box_raw[0] * scale_x, asset_box_raw[1] * scale_y, asset_box_raw[2] * scale_x, asset_box_raw[3] * scale_y)
                        overlap = _intersection(safe_pt, asset_box)
                        if overlap > 1e-9:
                            issues.append({"severity": "blocker", "code": "table_cell_asset_text_collision", "slide": slide_index, "cell_id": cell_id, "asset_id": asset.get("object_id") or asset.get("name"), "intersection_area": round(overlap, 9)})
                    size_value = style.get("size", style.get("font_size_pt", table.get("size", table.get("font_size_pt", theme.get("size", 12)))))
                    size = _number(size_value)
                    if size is None or size <= 0:
                        issues.append({"severity": "blocker", "code": "table_font_size_invalid", "slide": slide_index, "cell_id": cell_id, "font_size_pt": size_value})
                        size = 12.0
                    line_spacing_value = style.get("line_spacing", table.get("line_spacing", 1.2))
                    line_spacing = _number(line_spacing_value)
                    if line_spacing is None or line_spacing <= 0:
                        issues.append({"severity": "blocker", "code": "table_line_spacing_invalid", "slide": slide_index, "cell_id": cell_id, "line_spacing": line_spacing_value})
                        line_spacing = 1.2
                    line_height = size * line_spacing
                    cjk_units = sum(1.0 if ord(char) > 255 else 0.55 for char in text)
                    chars_per_line = max(1.0, safe_pt[2] / max(size, 1.0))
                    needed_lines = max(1, math.ceil(cjk_units / chars_per_line)) if text else 0
                    unbreakable_runs = re.findall(r"[A-Za-z0-9][A-Za-z0-9%./:+—-]*", text)
                    if unbreakable_runs:
                        longest_run = max(len(run) for run in unbreakable_runs)
                        if longest_run > chars_per_line + 1e-9:
                            issues.append({"severity": "blocker", "code": "table_cell_unbreakable_run_exceeded", "slide": slide_index, "cell_id": cell_id, "longest_run": longest_run, "chars_per_line": round(chars_per_line, 4)})
                    if needed_lines * line_height > safe_pt[3] + 1e-9:
                        issues.append({"severity": "blocker", "code": "table_cell_capacity_exceeded", "slide": slide_index, "cell_id": cell_id, "needed_lines": needed_lines, "available_height_pt": round(safe_pt[3], 6)})
                    if text:
                        density_metrics.append({"slide": slide_index, "cell_id": cell_id, "text_units": round(cjk_units, 4), "font_size_pt": size, "usable_width_pt": round(safe_pt[2], 4), "usable_height_pt": round(safe_pt[3], 4), "needed_lines": needed_lines, "line_capacity": round(safe_pt[3] / line_height, 4) if line_height > 0 else 0})
                    cx += column_width
                cy += row_height
    return {
        "schema": "ai-ppt-plus/table-layout-validation/v2",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "coordinate_space": units,
        "canvas": {"width": canvas_width, "height": canvas_height, "slide_width_pt": slide_width_pt, "slide_height_pt": slide_height_pt},
        "issues": issues,
        "density_metrics": density_metrics,
        "human_visual_review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        value = json.loads(Path(args.deck).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("layout must contain a JSON object")
        result = validate(value)
    except Exception as exc:
        result = {
            "schema": "ai-ppt-plus/table-layout-validation/v2",
            "valid": False,
            "status": "blocked",
            "coordinate_space": None,
            "issues": [{"severity": "blocker", "code": "table_layout_runtime_error", "message": f"{type(exc).__name__}: {exc}"}],
            "density_metrics": [],
            "human_visual_review_required": True,
        }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
