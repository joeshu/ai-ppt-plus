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
    print("table layout safety: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
