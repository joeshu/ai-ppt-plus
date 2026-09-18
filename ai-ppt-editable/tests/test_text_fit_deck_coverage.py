from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from text_fit_deck import TEXT_SLOT_KINDS, audit_layout


def test_text_fit_covers_native_text_table_and_all_chart_text_slots():
    deck = {
        "units": "fraction",
        "ref_width": 1536,
        "ref_height": 864,
        "slide_width_in": 13.333333,
        "slide_height_in": 7.5,
        "slides": [{
            "texts": [{"object_id": "body", "text": "正式正文", "x": 0.05, "y": 0.05, "w": 0.25, "h": 0.08, "size": 18}],
            "shapes": [{"object_id": "shape-label", "text": "形状标签", "x": 0.05, "y": 0.15, "w": 0.20, "h": 0.06, "size": 14}],
            "tables": [{
                "object_id": "table-1", "x": 0.05, "y": 0.25, "w": 0.30, "h": 0.12,
                "columns": 2, "size": 12, "rows": [["字段", "值"]],
            }],
            "charts": [{
                "object_id": "chart-1", "x": 0.40, "y": 0.10, "w": 0.50, "h": 0.50,
                "title": "收入趋势", "legend": True, "data_labels": True,
                "categories": ["1月", "2月", "3月"],
                "series": [
                    {"name": "2025年", "values": [100, 90, 80]},
                    {"name": "2026年", "values": [95, 85, None]},
                ],
            }],
        }],
    }
    with tempfile.TemporaryDirectory() as temp:
        layout = Path(temp) / "layout.json"
        layout.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        report = audit_layout(layout)
    assert report["valid"]
    assert set(report["coverage_by_kind"]) == set(TEXT_SLOT_KINDS)
    assert report["coverage_by_kind"] == {
        "text": 1,
        "shape_text": 1,
        "table_cell": 2,
        "chart_title": 1,
        "chart_legend": 2,
        "chart_category_label": 3,
        "chart_data_label": 5,
    }
    assert report["slot_count"] == 15
    assert len(report["measured_object_ids"]) == len(set(report["measured_object_ids"]))


if __name__ == "__main__":
    test_text_fit_covers_native_text_table_and_all_chart_text_slots()
    print("TextFit full-slot coverage: ok")
