from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reconstruction.difference_graph import DifferenceGraph
from reconstruction.manifest_bridge import build_page_graph
from reconstruction.repair_executors import RepairExecutionError, execute_plan
from reconstruction.repair_router import RepairRouter


def _layout():
    return {
        "project_id": "case-01",
        "slide_width_in": 13.333333,
        "slide_height_in": 7.5,
        "ref_width": 1600,
        "ref_height": 900,
        "slides": [{
            "texts": [{
                "object_id": "title_01",
                "x": 1.0,
                "y": 0.8,
                "w": 4.0,
                "h": 0.6,
                "text": "高质量发展",
                "font": "Noto Sans CJK SC",
                "font_size": 28,
                "runs": [{"text": "高质量", "bold": True}, {"text": "发展"}],
            }],
            "tables": [{
                "object_id": "table_01",
                "x": 1.0,
                "y": 3.0,
                "w": 7.0,
                "h": 2.0,
                "rows": [["A", "B"], ["1", "2"]],
                "native_required": True,
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
                    "object_id": "title_01",
                    "role": "formal-text",
                    "object_type": "editable_text",
                    "editability_level": "L1",
                    "text_spec": {
                        "text": "高质量发展",
                        "runs": [{"text": "高质量", "bold": True}, {"text": "发展"}],
                    },
                },
                {
                    "object_id": "table_01",
                    "role": "data-table",
                    "object_type": "editable_table",
                    "editability_level": "L1",
                    "data_snapshot": {"kind": "table", "values": [["A", "B"], ["1", "2"]]},
                },
            ],
        }],
    }


def test_manifest_bridge_preserves_text_and_table_semantics():
    graph = build_page_graph(_layout(), _manifest(), slide_no=1)
    assert graph.by_id("title_01").type == "text"
    assert graph.by_id("title_01").semantic["runs"][0]["text"] == "高质量"
    assert graph.by_id("table_01").type == "table"
    assert graph.by_id("table_01").semantic["native_required"] is True
    assert graph.by_id("table_01").bbox == (1.0, 3.0, 7.0, 2.0)


def test_typography_repair_mutates_only_target_text():
    diff = DifferenceGraph.from_dict({
        "version": "1.0",
        "source_id": "source.png",
        "rendered_id": "rendered.png",
        "findings": [{
            "id": "f_typo",
            "object_id": "title_01",
            "domain": "typography",
            "severity": "P1",
            "message": "title too large",
            "confidence": 0.98,
            "proposed_patch": {
                "font_size": 26.5,
                "line_spacing": 1.02,
                "runs": [{"text": "高质量", "bold": True, "color": "FF0000"}, {"text": "发展", "bold": True}],
            },
        }],
    })
    plan = RepairRouter().build_plan(diff)
    result = execute_plan(_layout(), plan)
    text = result["deck"]["slides"][0]["texts"][0]
    table = result["deck"]["slides"][0]["tables"][0]
    assert text["font_size"] == 26.5
    assert text["line_spacing"] == 1.02
    assert text["runs"][0]["color"] == "FF0000"
    assert table["rows"] == [["A", "B"], ["1", "2"]]
    assert result["report"]["applied"][0]["engine"] == "typography_repair"


def test_semantic_table_data_repair_preserves_native_type():
    diff = DifferenceGraph.from_dict({
        "version": "1.0",
        "source_id": "source.png",
        "rendered_id": "rendered.png",
        "findings": [{
            "id": "f_sem",
            "object_id": "table_01",
            "domain": "semantic",
            "severity": "P1",
            "message": "table values differ from approved snapshot",
            "confidence": 0.99,
            "proposed_patch": {
                "target_type": "table",
                "native_required": True,
                "table_data": [["A", "B"], ["3", "4"]],
            },
        }],
    })
    plan = RepairRouter().build_plan(diff)
    result = execute_plan(_layout(), plan)
    table = result["deck"]["slides"][0]["tables"][0]
    assert table["rows"] == [["A", "B"], ["3", "4"]]
    assert table["native_required"] is True


def test_semantic_cross_type_conversion_fails_closed():
    diff = DifferenceGraph.from_dict({
        "version": "1.0",
        "source_id": "source.png",
        "rendered_id": "rendered.png",
        "findings": [{
            "id": "f_sem2",
            "object_id": "title_01",
            "domain": "semantic",
            "severity": "P1",
            "message": "wrong semantic type",
            "confidence": 0.99,
            "proposed_patch": {"target_type": "table", "native_required": True},
        }],
    })
    plan = RepairRouter().build_plan(diff)
    try:
        execute_plan(_layout(), plan)
    except RepairExecutionError as exc:
        assert "cannot convert" in str(exc)
    else:
        raise AssertionError("expected cross-type semantic repair to fail closed")


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("reconstruction integration tests passed")
