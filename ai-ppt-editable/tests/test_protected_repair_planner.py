#!/usr/bin/env python3
"""B6 owner/protection/evidence/decision regression tests."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from protected_repair_planner import build_plan  # noqa: E402


def plan() -> dict:
    return {
        "schema": "ai-ppt-plus/authoring-plan/v1",
        "source": {"sha256": "0" * 64, "width_px": 100, "height_px": 100},
        "canvas": {"width": 1, "height": 1, "units": "normalized"},
        "objects": [
            {
                "object_id": "icon-1", "page": 1, "semantic_role": "pictogram",
                "implementation_type": "imagegen_asset", "bbox": [0.1, 0.1, 0.2, 0.2],
                "z_role": "asset", "protected_neighbors": ["footer"],
            },
            {
                "object_id": "footer", "page": 1, "semantic_role": "footer_system",
                "implementation_type": "native_shape", "bbox": [0.7, 0.1, 0.2, 0.2],
                "z_role": "container", "protected_neighbors": [],
            },
        ],
    }


def source() -> dict:
    return {"schema": "ai-ppt-plus/asset-render-coordinate-report/v2", "records": [{
        "object_id": "icon-1", "page": 1, "repair_required": True,
        "centroid_delta_px": [8, -3], "visible_bbox_delta_px": [6, -4, 10, -2],
        "repair": {"classification": "placement_only", "translate_px": [-8, 3], "scale_ratio": [0.95, 1.0], "regenerate_asset": False},
    }]}


def test_plan_maps_owner_and_protection() -> None:
    report = build_plan(plan(), source())
    assert report["valid"] is True
    action = report["actions"][0]
    assert action["owner"]["object_id"] == "icon-1"
    assert action["protected_neighbors"] == ["footer"]
    assert "translation_px" in action["responsible_parameters"]
    assert action["regenerate_asset"] is False
    assert action["forbidden_compensation"][0]["object_id"] == "footer"


def test_accept_requires_and_checks_protected_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="b6-planner-") as folder:
        root = Path(folder)
        from PIL import Image, ImageDraw

        before = root / "before"; after = root / "after"
        before.mkdir(); after.mkdir()
        for directory, owner_color in ((before, "red"), (after, "blue")):
            image = Image.new("RGB", (200, 100), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((20, 10, 60, 30), fill=owner_color)
            draw.rectangle((140, 10, 180, 30), fill="green")
            image.save(directory / "slide-1.png")
        report = build_plan(plan(), source(), decision="accept", before_render_dir=before, after_render_dir=after, evidence_dir=root / "evidence")
        assert report["valid"] is True, report
        assert report["status"] == "accepted"
        pair = report["actions"][0]["evidence"]["protected_neighbors"]["footer"]
        assert pair["material_regression"] is False
        assert Path(report["actions"][0]["evidence"]["owner"]["before"]["path"]).is_file()


def test_unknown_owner_fails_closed() -> None:
    bad = {"records": [{"object_id": "missing", "repair": {"classification": "placement_only"}}]}
    report = build_plan(plan(), bad)
    assert report["valid"] is False
    assert any(item["code"] == "repair_owner_unknown" for item in report["issues"])


def test_aligned_coordinate_rows_are_not_repair_actions() -> None:
    aligned = {
        "schema": "ai-ppt-plus/asset-render-coordinate-report/v2",
        "records": [{"object_id": "icon-1", "repair_required": False, "repair": {"classification": "aligned"}}],
    }
    report = build_plan(plan(), aligned)
    assert report["valid"] is True
    assert report["status"] == "no-repair-required"
    assert report["action_count"] == 0


if __name__ == "__main__":
    test_plan_maps_owner_and_protection()
    test_accept_requires_and_checks_protected_evidence()
    test_unknown_owner_fails_closed()
    test_aligned_coordinate_rows_are_not_repair_actions()
    print("B6 protected repair planner tests passed")
