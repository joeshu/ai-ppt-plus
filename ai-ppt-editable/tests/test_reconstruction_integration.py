from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reconstruction.difference_graph import DifferenceGraph
from reconstruction.evidence_bridge import from_dual_comparison, merge_difference_graphs
from reconstruction.manifest_bridge import build_page_graph
from reconstruction.repair_executors import RepairExecutionError, execute_plan
from reconstruction.repair_router import RepairRouter


def _layout():
    return {
        "project_id": "case-01",
        "units": "inches",
        "slide_width_in": 13.333333,
        "slide_height_in": 7.5,
        "ref_width": 1600,
        "ref_height": 900,
        "slides": [{
            "texts": [{
                "object_id": "title_01", "x": 1.0, "y": 0.8, "w": 4.0, "h": 0.6,
                "text": "高质量发展", "font": "Noto Sans CJK SC", "font_size": 28,
                "runs": [{"text": "高质量", "bold": True}, {"text": "发展"}],
            }],
            "tables": [{
                "object_id": "table_01", "x": 1.0, "y": 3.0, "w": 7.0, "h": 2.0,
                "rows": [["A", "B"], ["1", "2"]], "native_required": True,
            }],
            "icons": [{
                "object_id": "icon_01", "x": 10.0, "y": 1.0, "w": 1.0, "h": 1.0,
                "file": "assets/icon.png", "asset_policy": "normal_asset",
            }, {
                "object_id": "brand_01", "x": 11.2, "y": 0.5, "w": 1.2, "h": 0.5,
                "file": "assets/logo.png", "asset_policy": "brand_lockup",
                "brand_asset_contract": {"whole_asset": True, "allow_crop": False},
            }],
        }],
    }


def _manifest():
    return {
        "schema": "ai-ppt-plus/slide-object-manifest/v1",
        "project_id": "case-01",
        "slides": [{
            "slide_no": 1,
            "objects": [
                {
                    "object_id": "title_01", "role": "formal-text", "object_type": "editable_text",
                    "editability_level": "L1",
                    "text_spec": {"text": "高质量发展", "runs": [{"text": "高质量", "bold": True}, {"text": "发展"}]},
                },
                {
                    "object_id": "table_01", "role": "data-table", "object_type": "editable_table",
                    "editability_level": "L1",
                    "data_snapshot": {"kind": "table", "values": [["A", "B"], ["1", "2"]]},
                },
            ],
        }],
    }


def _plan(domain: str, object_id: str, patch: dict, *, severity: str = "P1"):
    graph = DifferenceGraph.from_dict({
        "version": "1.0", "source_id": "source.png", "rendered_id": "rendered.png",
        "findings": [{
            "id": f"f_{domain}_{object_id}", "object_id": object_id, "domain": domain,
            "severity": severity, "message": f"{domain} mismatch", "confidence": 0.99,
            "proposed_patch": patch,
        }],
    })
    return RepairRouter().build_plan(graph)


def test_manifest_bridge_preserves_text_and_table_semantics():
    graph = build_page_graph(_layout(), _manifest(), slide_no=1)
    assert graph.by_id("title_01").type == "text"
    assert graph.by_id("title_01").semantic["runs"][0]["text"] == "高质量"
    assert graph.by_id("table_01").type == "table"
    assert graph.by_id("table_01").semantic["native_required"] is True
    assert graph.by_id("table_01").bbox == (1.0, 3.0, 7.0, 2.0)


def test_geometry_repair_is_exact_and_bounded():
    result = execute_plan(_layout(), _plan("geometry", "title_01", {"x": 1.2, "y": 0.9, "w": 4.2, "h": 0.62}))
    text = result["deck"]["slides"][0]["texts"][0]
    assert (text["x"], text["y"], text["w"], text["h"]) == (1.2, 0.9, 4.2, 0.62)
    try:
        execute_plan(_layout(), _plan("geometry", "title_01", {"x": 13.0, "w": 4.0}))
    except RepairExecutionError as exc:
        assert "outside slide bounds" in str(exc)
    else:
        raise AssertionError("expected out-of-bounds geometry to fail closed")


def test_typography_repair_mutates_only_target_text():
    patch = {
        "font_size": 26.5, "line_spacing": 1.02,
        "runs": [{"text": "高质量", "bold": True, "color": "FF0000"}, {"text": "发展", "bold": True}],
    }
    result = execute_plan(_layout(), _plan("typography", "title_01", patch))
    text = result["deck"]["slides"][0]["texts"][0]
    table = result["deck"]["slides"][0]["tables"][0]
    assert text["font_size"] == 26.5
    assert text["line_spacing"] == 1.02
    assert text["runs"][0]["color"] == "FF0000"
    assert table["rows"] == [["A", "B"], ["1", "2"]]


def test_asset_transform_and_regeneration_boundary():
    result = execute_plan(_layout(), _plan("asset", "icon_01", {"scale": 1.2, "rotation": 5, "opacity": 0.9}))
    icon = result["deck"]["slides"][0]["icons"][0]
    assert round(icon["w"], 4) == 1.2 and round(icon["h"], 4) == 1.2
    assert icon["rotation"] == 5.0 and icon["opacity"] == 0.9

    regen = execute_plan(_layout(), _plan("asset", "icon_01", {
        "regenerate": True, "generation_prompt": "white outline cloud icon", "background_mode": "transparent"
    }))
    assert regen["report"]["requires_external_asset_generation"] is True
    request = regen["report"]["regeneration_requests"][0]
    assert request["object_id"] == "icon_01"
    assert request["preserve_geometry"]["x"] == 10.0


def test_brand_asset_crop_is_forbidden():
    try:
        execute_plan(_layout(), _plan("asset", "brand_01", {"crop": {"left": 0.1}}))
    except RepairExecutionError as exc:
        assert "forbids crop" in str(exc)
    else:
        raise AssertionError("expected brand crop to fail closed")


def test_semantic_table_data_repair_preserves_native_type():
    patch = {"target_type": "table", "native_required": True, "table_data": [["A", "B"], ["3", "4"]]}
    result = execute_plan(_layout(), _plan("semantic", "table_01", patch))
    table = result["deck"]["slides"][0]["tables"][0]
    assert table["rows"] == [["A", "B"], ["3", "4"]]
    assert table["native_required"] is True


def test_semantic_cross_type_conversion_fails_closed():
    try:
        execute_plan(_layout(), _plan("semantic", "title_01", {"target_type": "table", "native_required": True}))
    except RepairExecutionError as exc:
        assert "cannot convert" in str(exc)
    else:
        raise AssertionError("expected cross-type semantic repair to fail closed")


def test_dual_comparison_evidence_does_not_invent_geometry_patch():
    deterministic = from_dual_comparison({
        "valid": False,
        "pixel_comparison": {
            "status": "blocked", "metrics": {"blurred_layout_ssim": 0.86, "pixel_fidelity_score": 0.80},
            "bindings": [{"reference": {"path": "source.png"}, "rendered": {"path": "render.png"}}],
        },
        "object_comparison": {
            "status": "blocked", "errors": [{"code": "wrong_object_type", "object_id": "table_01", "message": "expected native table", "expected_type": "table", "native_required": True}],
            "warnings": [],
        },
        "issues": [],
    })
    visual = deterministic.by_domain("geometry")[0]
    semantic = deterministic.by_domain("semantic")[0]
    assert visual.severity == "P1" and visual.proposed_patch == {}
    assert semantic.object_id == "table_01"
    assert semantic.proposed_patch == {"target_type": "table", "native_required": True}

    astra = DifferenceGraph.from_dict({
        "version": "1.0", "source_id": "source.png", "rendered_id": "render.png",
        "findings": [{
            "id": "astra:title", "object_id": "title_01", "domain": "geometry", "severity": "P1",
            "message": "title width too narrow", "confidence": 0.96, "proposed_patch": {"w": 4.2}
        }],
    })
    merged = merge_difference_graphs(deterministic, astra)
    assert any(item.id.startswith("det:semantic") for item in merged.findings)
    assert any(item.id == "astra:title" for item in merged.findings)
    assert len(merged.blocking()) >= 3


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("reconstruction integration tests passed")
