#!/usr/bin/env python3
"""Regression coverage for explicit layout and AuthoringPlan coordinates."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COORDINATE = ROOT / "ai-ppt-editable" / "scripts" / "validate_coordinate_space.py"
AUTHORING = ROOT / "ai-ppt-editable" / "scripts" / "validate_authoring_plan.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def plan(units: str, width: float, height: float, bbox: list[float]) -> dict:
    return {
        "schema": "ai-ppt-plus/authoring-plan/v1",
        "source": {"sha256": "a" * 64, "width_px": 1536, "height_px": 864},
        "canvas": {"width": width, "height": height, "units": units},
        "coordinate_space": {"normalized": "normalized", "px": "reference_pixels"}[units],
        "objects": [{
            "object_id": "title", "page": 1, "semantic_role": "title",
            "implementation_type": "native_text", "bbox": bbox, "bbox_units": {"normalized": "normalized", "px": "reference_pixels"}[units],
            "z_role": "text", "typography_contract": {},
        }],
    }


def main() -> int:
    coordinate = load(COORDINATE, "validate_coordinate_space")
    authoring = load(AUTHORING, "validate_authoring_plan_coordinates")

    valid_fraction = coordinate.validate({
        "units": "fraction",
        "coordinate_space": "normalized",
        "slides": [{"texts": [{"object_id": "title", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.1}], "shapes": [{"object_id": "rule", "type": "line", "x": 0.1, "y": 0.25, "w": 0.5, "h": 0}]}],
    })
    assert valid_fraction["valid"], valid_fraction

    invalid_units = coordinate.validate({
        "units": "fraction",
        "slides": [{"tables": [{"object_id": "table", "bbox": [0, 0, 1536, 864], "rows": [["A"]]}]}],
    })
    assert not invalid_units["valid"]
    assert "object_out_of_canvas" in {item["code"] for item in invalid_units["issues"]}

    valid_px = coordinate.validate({
        "units": "px", "coordinate_space": "reference_pixels", "ref_width": 1536, "ref_height": 864,
        "slides": [{"texts": [{"object_id": "title", "x": 100, "y": 80, "w": 500, "h": 60}]}],
    })
    assert valid_px["valid"], valid_px

    assert authoring.validate(plan("px", 1536, 864, [100, 80, 500, 60]))["valid"]
    bad = plan("px", 1536, 864, [1400, 800, 200, 100])
    bad["coordinate_space"] = "normalized"
    result = authoring.validate(bad)
    codes = {item["code"] for item in result["issues"]}
    assert "authoring_plan_coordinate_space_mismatch" in codes
    assert "authoring_plan_bbox_invalid" in codes
    print("coordinate space contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
