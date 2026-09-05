from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reconstruction.difference_graph import DifferenceGraph
from reconstruction.graph_ir import GraphValidationError, PageGraph
from reconstruction.quality_gate import QualityGate
from reconstruction.repair_router import RepairRouter


def _page_graph() -> PageGraph:
    return PageGraph.from_dict({
        "version": "1.0",
        "page": {
            "slide_width_in": 13.333333,
            "slide_height_in": 7.5,
            "reference_width": 1600,
            "reference_height": 900,
        },
        "nodes": [
            {"id": "card_01", "type": "group", "bbox": [1.0, 1.0, 3.0, 2.0]},
            {
                "id": "title_01",
                "type": "text",
                "bbox": [1.2, 1.2, 2.4, 0.5],
                "parent_id": "card_01",
                "semantic": {
                    "text": "高质量发展",
                    "runs": [
                        {"text": "高质量", "bold": True, "color": "FF0000"},
                        {"text": "发展", "bold": True, "color": "FFFFFF"},
                    ],
                },
                "relations": [{"kind": "belongs_to", "target": "card_01", "confidence": 0.99}],
            },
            {
                "id": "table_01",
                "type": "table",
                "bbox": [1.0, 4.0, 8.0, 2.0],
                "semantic": {"rows": [["A", "B"], ["1", "2"]]},
            },
        ],
    })


def test_page_graph_projects_native_semantics():
    graph = _page_graph()
    deck = graph.to_authoring_deck(assets_dir="assets")
    assert deck["require_native_structure"] is True
    assert deck["slides"][0]["texts"][0]["runs"][0]["text"] == "高质量"
    assert deck["slides"][0]["tables"][0]["native_required"] is True


def test_page_graph_rejects_unknown_relation_target():
    payload = {
        "page": {"slide_width_in": 13.333, "slide_height_in": 7.5, "reference_width": 1600, "reference_height": 900},
        "nodes": [{
            "id": "a",
            "type": "text",
            "bbox": [0, 0, 1, 1],
            "relations": [{"kind": "belongs_to", "target": "missing"}],
        }],
    }
    try:
        PageGraph.from_dict(payload)
    except GraphValidationError as exc:
        assert "unknown relation target" in str(exc)
    else:
        raise AssertionError("expected GraphValidationError")


def test_repair_router_allows_bounded_geometry_patch():
    diff = DifferenceGraph.from_dict({
        "version": "1.0",
        "source_id": "source.png",
        "rendered_id": "rendered.png",
        "findings": [{
            "id": "f1",
            "object_id": "title_01",
            "domain": "geometry",
            "severity": "P1",
            "message": "title is too narrow",
            "confidence": 0.97,
            "proposed_patch": {"w": 2.7, "x": 1.1},
        }],
    })
    plan = RepairRouter().build_plan(diff)
    assert len(plan.actions) == 1
    assert plan.actions[0].engine == "geometry_repair"
    assert not plan.deferred


def test_repair_router_defers_semantic_p0():
    diff = DifferenceGraph.from_dict({
        "version": "1.0",
        "source_id": "source.png",
        "rendered_id": "rendered.png",
        "findings": [{
            "id": "f2",
            "object_id": "table_01",
            "domain": "semantic",
            "severity": "P0",
            "message": "table was rasterized",
            "confidence": 0.99,
            "proposed_patch": {"target_type": "table", "native_required": True},
        }],
    })
    plan = RepairRouter().build_plan(diff)
    assert not plan.actions
    assert plan.has_blocking_deferred


def test_quality_gate_fails_closed_on_raster_or_p1():
    diff = DifferenceGraph.from_dict({
        "version": "1.0",
        "source_id": "source.png",
        "rendered_id": "rendered.png",
        "findings": [{
            "id": "f3",
            "object_id": "illustration_01",
            "domain": "asset",
            "severity": "P1",
            "message": "hero scale mismatch",
            "confidence": 0.94,
            "proposed_patch": {"scale": 1.08},
        }],
    })
    result = QualityGate().evaluate(
        differences=diff,
        global_visual_similarity=0.97,
        critical_region_scores={"title": 0.96},
        editable_ratio=1.0,
        semantic_accuracy=1.0,
        full_slide_raster_detected=True,
        renderer_regressions=[],
    )
    assert result.passed is False
    assert any("full-slide raster" in item for item in result.failures)
    assert any("P1 asset" in item for item in result.failures)


def main() -> int:
    tests = [
        test_page_graph_projects_native_semantics,
        test_page_graph_rejects_unknown_relation_target,
        test_repair_router_allows_bounded_geometry_patch,
        test_repair_router_defers_semantic_p0,
        test_quality_gate_fails_closed_on_raster_or_p1,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS reconstruction contract suite ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
