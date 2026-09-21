#!/usr/bin/env python3
"""Regression coverage for dense native-table text and overlay-asset safety."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_table_layout import validate  # noqa: E402


def main() -> int:
    base = {
        "units": "fraction", "slide_height_in": 7.5, "theme": {"size": 10},
        "slides": [{
            "tables": [{"object_id": "actions", "x": .1, "y": .5, "w": .8, "h": .3,
                        "rows": [["图标通道", "较短正文"], ["第二行", "另一段正文"]],
                        "column_widths": [.2, .6], "row_heights": [.15, .15],
                        "cell_margins": {"left": 55, "right": 4, "top": 2, "bottom": 2}}],
            "icons": [{"object_id": "action-icon", "x": .115, "y": .54, "w": .04, "h": .04}],
        }],
    }
    valid = validate(base)
    assert valid["valid"] is True, valid
    collision = {**base, "slides": [{**base["slides"][0], "icons": [{"object_id": "action-icon", "x": .19, "y": .54, "w": .06, "h": .05}]}]}
    result = validate(collision)
    assert result["valid"] is False
    assert any(item["code"] == "table_cell_asset_text_collision" for item in result["issues"])
    dense = {**base, "slides": [{**base["slides"][0], "tables": [{**base["slides"][0]["tables"][0], "rows": [["图标通道", "非常密集的中文文字" * 100], ["第二行", "正文"]]}]}]}
    result = validate(dense)
    assert result["valid"] is False
    assert any(item["code"] == "table_cell_capacity_exceeded" for item in result["issues"])

    px_table = {**base["slides"][0]["tables"][0], "x": 153.6, "y": 432.0, "w": 1228.8, "h": 259.2, "column_widths": [307.2, 921.6], "row_heights": [129.6, 129.6]}
    px = {**base, "units": "px", "ref_width": 1536, "ref_height": 864, "slides": [{
        "tables": [px_table],
        "icons": [{"object_id": "action-icon", "x": 176.64, "y": 466.56, "w": 61.44, "h": 34.56}],
    }]}
    result = validate(px)
    assert result["valid"] is True, result
    assert result["coordinate_space"] == "px"
    assert result["density_metrics"]

    empty = {**base, "slides": [{"tables": [{"object_id": "empty", "bbox": [0.1, 0.1, 0.4, 0.2], "rows": []}]}]}
    result = validate(empty)
    assert result["valid"] is False
    assert "table_rows_missing" in {item["code"] for item in result["issues"]}
    print("table layout safety: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
