#!/usr/bin/env python3
"""Convert semantically repeated information tables into native primitives.

The conversion preserves the existing icon assets and their coordinates. It
only changes the authoring model: row rectangles/dividers become shapes and
each title/body becomes its own native text box.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


def _border_color(table: dict) -> str:
    border = table.get("border") or {}
    all_border = border.get("all") if isinstance(border, dict) else {}
    return str((all_border or {}).get("color") or "#D6E2F0")


def _border_width(table: dict) -> float:
    border = table.get("border") or {}
    all_border = border.get("all") if isinstance(border, dict) else {}
    return float((all_border or {}).get("width") or 0.5)


def convert(deck: dict) -> dict:
    result = copy.deepcopy(deck)
    for slide in result.get("slides", []):
        if not isinstance(slide, dict):
            continue
        original_tables = list(slide.get("tables", []) or [])
        kept_tables = []
        semantic_regions = list(slide.get("semantic_regions", []) or [])
        shapes = list(slide.get("shapes", []) or [])
        texts = list(slide.get("texts", []) or [])
        for table in original_tables:
            semantic_type = str(table.get("semantic_type") or "").casefold()
            associated = list(table.get("associated_icon_ids") or [])
            # A table-like region with no data source/schema but with icons
            # anchored inside its rows is a repeated information component.
            # This keeps the correction useful for legacy manifests that did
            # not yet emit semantic_type.
            has_icon_overlap = False
            tx, ty, tw, th = (float(table.get(key, 0)) for key in ("x", "y", "w", "h"))
            for icon in slide.get("icons", []) or []:
                if not isinstance(icon, dict):
                    continue
                ix, iy, iw, ih = (float(icon.get(key, 0)) for key in ("x", "y", "w", "h"))
                if max(tx, ix) < min(tx + tw, ix + iw) and max(ty, iy) < min(ty + th, iy + ih):
                    has_icon_overlap = True
                    icon_id = icon.get("object_id") or icon.get("name")
                    if icon_id and icon_id not in associated:
                        associated.append(icon_id)
            is_repeated = semantic_type in {"repeated_component_group", "information_list", "card_list"} or (
                has_icon_overlap and not table.get("data_source") and not table.get("field_schema") and not table.get("data_snapshot")
            )
            if not is_repeated:
                kept_tables.append(table)
                continue
            x, y, w, h = (float(table.get(key, 0)) for key in ("x", "y", "w", "h"))
            rows = table.get("rows") or []
            widths = list(table.get("column_widths") or [])
            heights = list(table.get("row_heights") or [])
            if len(widths) != 2 or len(heights) != len(rows):
                raise ValueError(f"{table.get('object_id')}: repeated component requires two columns and row heights")
            col0 = widths[0]
            cursor_y = y
            title_styles = table.get("cell_styles") or {}
            child_ids = []
            items = []
            for row_index, (row, row_height) in enumerate(zip(rows, heights)):
                if len(row) != 2:
                    raise ValueError(f"{table.get('object_id')}: repeated component rows must have two cells")
                title = str(row[0])
                body = str(row[1])
                row_id = f"{table.get('object_id')}-item-{row_index + 1}"
                child_ids.append(row_id)
                title_id = f"{row_id}-title"
                body_id = f"{row_id}-body"
                background_id = f"{row_id}-background"
                divider_id = f"{row_id}-separator"
                icon_id = associated[row_index] if row_index < len(associated) else None
                items.append({
                    "item_id": row_id,
                    "icon_ids": [str(icon_id)] if icon_id else [],
                    "title_object_id": title_id,
                    "body_object_id": body_id,
                    "background_object_id": background_id,
                    "divider_object_id": divider_id,
                })
                shapes.append({
                    "object_id": background_id, "type": "rect", "x": x,
                    "y": cursor_y, "w": w, "h": row_height, "fill": "#FFFFFF",
                    "line": _border_color(table), "line_width": _border_width(table),
                })
                shapes.append({
                    "object_id": divider_id, "type": "line", "x": x + col0,
                    "y": cursor_y, "x2": x + col0, "y2": cursor_y + row_height,
                    "line": _border_color(table), "line_width": _border_width(table),
                })
                title_style = title_styles.get(f"{row_index},0", {}) if isinstance(title_styles, dict) else {}
                title_style = title_style if isinstance(title_style, dict) else {}
                texts.append({
                    "object_id": title_id, "text": title,
                    "x": x + 0.038, "y": cursor_y + 0.010,
                    "w": max(0.01, col0 - 0.041), "h": max(0.02, row_height - 0.018),
                    "size": float(title_style.get("size", table.get("size", 8.5))),
                    "bold": bool(title_style.get("bold", True)),
                    "color": str(title_style.get("color") or "#222222"),
                    "align": "left", "anchor": "middle",
                })
                texts.append({
                    "object_id": body_id, "text": body,
                    "x": x + col0 + 0.006, "y": cursor_y + 0.007,
                    "w": max(0.01, w - col0 - 0.010), "h": max(0.02, row_height - 0.014),
                    "size": float(table.get("size", 7.5)), "color": str(table.get("color") or "#222222"),
                    "align": "left", "anchor": "middle",
                })
                cursor_y += row_height
            semantic_regions.append({
                "object_id": table.get("object_id"),
                "object_type": "repeated_component_group",
                "children": child_ids,
                "items": items,
                "requires_independent_children": True,
                "independent_item_count": len(child_ids),
                "source_semantic_type": "icon_title_description_list",
            })
        slide["tables"] = kept_tables
        slide["shapes"] = shapes
        slide["texts"] = texts
        slide["semantic_regions"] = semantic_regions
    result["semantic_layout_policy"] = "table-vs-repeated-component-v1"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    deck = json.loads(Path(args.input).read_text(encoding="utf-8"))
    converted = convert(deck)
    Path(args.output).write_text(json.dumps(converted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
