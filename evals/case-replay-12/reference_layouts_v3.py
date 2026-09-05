"""Targeted third-pass refinements for frozen reference replay layouts."""
from __future__ import annotations

from reference_layouts_v2 import fttr_policy_layout_v2


def _shift_y(item, amount: float) -> None:
    if isinstance(item, dict) and isinstance(item.get("y"), (int, float)):
        item["y"] = float(item["y"]) + amount


def fttr_policy_layout_v3(case, run_dir, optimized, h):
    deck = fttr_policy_layout_v2(case, run_dir, optimized, h)
    slide = deck["slides"][0]

    # Frozen reference analysis: bottom policy/table region begins ~19 px lower
    # than v2 at 1080p. Shift the whole region together to preserve relations.
    dy = 0.018
    bottom_group_ids = {"policy-table-tab", "subsidy-table-tab"}
    bottom_text_ids = {
        "policy-table-tab-icon", "policy-table-tab-text",
        "subsidy-table-tab-icon", "subsidy-table-tab-text", "subsidy-unit",
        "policy-note", "subsidy-note",
    }
    for group in slide.get("groups", []) or []:
        if group.get("object_id") in bottom_group_ids:
            _shift_y(group, dy)
    for text in slide.get("texts", []) or []:
        if text.get("object_id") in bottom_text_ids:
            _shift_y(text, dy)
    for table in slide.get("tables", []) or []:
        if table.get("object_id") in {"policy-merged-table", "monthly-subsidy-table"}:
            _shift_y(table, dy)

    # Shape overlays authored before tables are hidden by the table graphic
    # frame. Remove those dead overlays and express progress in native cell
    # rich text instead so z-order cannot erase the visual signal.
    slide["shapes"] = [
        item for item in (slide.get("shapes", []) or [])
        if not str(item.get("object_id", "")).startswith("progress-")
    ]

    monthly = next(
        table for table in slide.get("tables", [])
        if table.get("object_id") == "monthly-subsidy-table"
    )
    styles = monthly.setdefault("cell_styles", {})
    styles["0,0"] = {
        "fill": "#073E78", "color": "#FFFFFF", "bold": True,
        "size": 7.2, "align": 2, "valign": "mid",
    }
    styles["6,0"] = {
        "fill": "#FFF0F2", "color": "#E60012", "bold": True,
        "size": 8.2, "align": 2, "valign": "mid",
    }

    bars = [
        ("20%", "▰▱▱▱▱"),
        ("45%", "▰▰▱▱▱"),
        ("70%", "▰▰▰▰▱"),
        ("60%", "▰▰▰▱▱"),
        ("85%", "▰▰▰▰▰"),
    ]
    rows = monthly.get("rows") or []
    for row_index, (label, bar) in enumerate(bars, 1):
        if row_index >= len(rows) or len(rows[row_index]) < 6:
            continue
        rows[row_index][5] = {
            "runs": [
                {"text": bar + "  ", "color": "#2F7DE1", "bold": True, "size": 7.4},
                {"text": label, "color": "#0969C8", "bold": True, "size": 7.8},
            ]
        }
    return deck


REFERENCE_BUILDERS_V3 = {
    "native-table-merge-richtext-01": fttr_policy_layout_v3,
}


def build_reference_layout_v3(case, run_dir, optimized, helpers):
    builder = REFERENCE_BUILDERS_V3.get(case.get("case_id"))
    if builder is None:
        return None
    return builder(case, run_dir, optimized, helpers)
