#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "text_slot_repair_planner.py"
spec = importlib.util.spec_from_file_location("text_slot_repair_planner", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def plan(objects, slots):
    return mod.build_plan(
        {"schema": "ai-ppt-plus/text-fit-deck/v3", "slots": slots},
        {"schema": "ai-ppt-plus/authoring-plan/v1", "source": {"width_px": 1000, "height_px": 500}, "objects": objects},
    )


def main():
    result = plan(
        [
            {"object_id": "title", "page": 1, "bbox": [0.10, 0.10, 0.20, 0.10], "protected_neighbors": ["icon"], "typography_contract": {}},
            {"object_id": "icon", "page": 1, "bbox": [0.50, 0.10, 0.10, 0.10]},
        ],
        [{"object_id": "text:title", "slide": 1, "geometry_defect": True, "geometry_fits": False, "box_deficit_px": [80, 0], "target_pt": 24, "recommended_pt": 21, "line_topology_preserved": True}],
    )
    action = result["actions"][0]
    assert action["selected_step"] == "slot_bbox", action
    assert action["responsible_parameters"] == ["bbox"]
    assert action["proposed_patch"]["bbox"][2] == 0.28
    assert action["protected_neighbors"] == ["icon"]
    assert action["font_shrink_last"] is True

    result = plan(
        [{"object_id": "caption", "page": 1, "bbox": [0.10, 0.20, 0.25, 0.10], "typography_contract": {}}],
        [{"object_id": "text:caption", "geometry_defect": True, "geometry_fits": False, "box_deficit_px": [0, 25], "target_pt": 16, "recommended_pt": 15, "line_topology_preserved": True}],
    )
    action = result["actions"][0]
    assert action["selected_step"] == "slot_bbox"
    assert action["proposed_patch"]["growth_px"] == [0.0, 25.0]
    assert action["proposed_patch"]["bbox"][3] == 0.15

    result = plan(
        [
            {"object_id": "card-a", "page": 1, "bbox": [0.05, 0.40, 0.20, 0.12], "component_family": "kpi-card", "typography_contract": {}},
            {"object_id": "card-b", "page": 1, "bbox": [0.35, 0.40, 0.20, 0.12], "component_family": "kpi-card", "typography_contract": {}},
        ],
        [
            {"object_id": "text:card-a", "geometry_defect": True, "geometry_fits": False, "box_deficit_px": [20, 0], "target_pt": 18, "recommended_pt": 17, "line_topology_preserved": True},
            {"object_id": "text:card-b", "geometry_defect": True, "geometry_fits": False, "box_deficit_px": [60, 0], "target_pt": 18, "recommended_pt": 15, "line_topology_preserved": True},
        ],
    )
    assert result["actions"][0]["proposed_patch"]["growth_px"] != result["actions"][1]["proposed_patch"]["growth_px"]

    result = plan(
        [
            {"object_id": "body", "page": 1, "bbox": [0.80, 0.10, 0.20, 0.20], "protected_neighbors": ["right"], "typography_contract": {"margins_px": [12, 8, 12, 8], "min_margins_px": [4, 4, 4, 4]}},
            {"object_id": "right", "page": 1, "bbox": [0.76, 0.08, 0.04, 0.24]},
        ],
        [{"object_id": "text:body", "geometry_defect": True, "geometry_fits": False, "box_deficit_px": [12, 4], "target_pt": 18, "recommended_pt": 16, "line_topology_preserved": True}],
    )
    action = result["actions"][0]
    assert action["selected_step"] == "text_margins", action
    assert action["responsible_parameters"] == ["margins"]
    assert action["proposed_patch"]["margins_px"] != [12, 8, 12, 8]

    result = plan(
        [{"object_id": "metric", "page": 1, "bbox": [0.1, 0.1, 0.3, 0.1], "typography_contract": {}}],
        [{"object_id": "text:metric", "geometry_defect": False, "geometry_fits": True, "topology_defect": True, "line_topology_preserved": False, "target_lines": 2, "line_count": 3, "box_deficit_px": [0, 0], "target_pt": 20, "recommended_pt": 18}],
    )
    action = result["actions"][0]
    assert action["selected_step"] == "reference_line_topology", action
    assert action["responsible_parameters"] == ["bbox"]
    assert action["proposed_patch"]["mode"] == "preserve_text_content_reflow_only"

    result = plan(
        [{"object_id": "hero", "page": 1, "bbox": [0, 0, 1, 1], "typography_contract": {"min_font_size_pt": 16}}],
        [{"object_id": "text:hero", "geometry_defect": True, "geometry_fits": False, "box_deficit_px": [20, 10], "target_pt": 24, "recommended_pt": 20, "line_topology_preserved": True}],
    )
    action = result["actions"][0]
    assert action["selected_step"] == "font_size_last", action
    assert action["responsible_parameters"] == ["font_size"]
    assert [row["step"] for row in action["candidates"]] == mod.REPAIR_ORDER

    result = plan([], [{"object_id": "text:missing", "geometry_defect": True, "box_deficit_px": [10, 0]}])
    assert result["valid"] is False
    assert result["issues"][0]["code"] == "text_slot_owner_unknown"
    print("text-slot repair planner tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
