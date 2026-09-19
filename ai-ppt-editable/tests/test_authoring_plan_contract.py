from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_authoring_plan.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_authoring_plan", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def valid_plan():
    return {
        "schema": "ai-ppt-plus/authoring-plan/v1",
        "source": {
            "path": "reference.png",
            "sha256": "1" * 64,
            "width_px": 1536,
            "height_px": 864,
            "page_count": 1,
        },
        "canvas": {"width": 1.0, "height": 1.0, "units": "normalized"},
        "objects": [
            {
                "object_id": "footer",
                "page": 1,
                "semantic_role": "footer_system",
                "implementation_type": "imagegen_asset",
                "bbox": [0.0, 0.85, 1.0, 0.15],
                "parent_id": None,
                "z_role": "asset",
                "protected_neighbors": ["footer-label"],
                "asset_contract": {
                    "semantic_identity": "wave skyline footer",
                    "color_roles": {"foreground": "red", "host": "transparent"},
                    "contour_traits": ["continuous wave"],
                    "alpha_required": True,
                    "safe_zone": "reference visible padding",
                    "provenance_mode": "imagegen",
                },
            },
            {
                "object_id": "footer-label",
                "page": 1,
                "semantic_role": "footer_label",
                "implementation_type": "native_text",
                "bbox": [0.03, 0.91, 0.25, 0.05],
                "parent_id": "footer",
                "z_role": "text",
                "protected_neighbors": ["footer"],
                "typography_contract": {
                    "target_lines": 1,
                    "alignment": "left",
                    "font_role": "footer",
                    "slot_reservations": [],
                },
            },
        ],
    }


def test_valid_authoring_plan_passes():
    result = load_module().validate(valid_plan())
    assert result["valid"] is True
    assert result["issues"] == []


def test_duplicate_ids_fail_closed():
    plan = valid_plan()
    plan["objects"].append(dict(plan["objects"][0]))
    result = load_module().validate(plan)
    assert result["valid"] is False
    assert any(item["code"] == "authoring_plan_object_id_duplicate" for item in result["issues"])


def test_missing_type_contract_fails_closed():
    plan = valid_plan()
    plan["objects"][1].pop("typography_contract")
    result = load_module().validate(plan)
    assert any(item["code"] == "authoring_plan_type_contract_missing" for item in result["issues"])


def test_unknown_parent_and_neighbor_fail_closed():
    plan = valid_plan()
    plan["objects"][1]["parent_id"] = "missing-parent"
    plan["objects"][1]["protected_neighbors"] = ["missing-neighbor"]
    result = load_module().validate(plan)
    codes = {item["code"] for item in result["issues"]}
    assert "authoring_plan_parent_unknown" in codes
    assert "authoring_plan_protected_neighbor_unknown" in codes


def test_parent_cycle_fails_closed():
    plan = valid_plan()
    plan["objects"][0]["parent_id"] = "footer-label"
    result = load_module().validate(plan)
    assert any(item["code"] == "authoring_plan_parent_cycle" for item in result["issues"])


def test_bbox_must_be_normalized_and_inside_canvas():
    plan = valid_plan()
    plan["objects"][0]["bbox"] = [0.9, 0.9, 0.2, 0.2]
    result = load_module().validate(plan)
    assert any(item["code"] == "authoring_plan_bbox_invalid" for item in result["issues"])
