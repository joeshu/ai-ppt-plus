from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reconstruction.batch_ingestion import AstraIngestionError, convergence_delta, ingest_astra_qa
from reconstruction.difference_graph import DifferenceGraph
from reconstruction.graph_ir import PageGraph


def _page():
    return PageGraph.from_dict({
        "version": "1.0",
        "page": {"slide_width_in": 13.333, "slide_height_in": 7.5, "reference_width": 1920, "reference_height": 1080},
        "nodes": [
            {"id": "title", "type": "text", "bbox": [0.1, 0.1, 0.4, 0.08], "semantic": {"text": "标题"}},
            {"id": "icon", "type": "icon", "bbox": [0.8, 0.1, 0.08, 0.08]},
        ],
    })


def _deterministic():
    return DifferenceGraph.from_dict({
        "version": "1.0",
        "source_id": "reference.png",
        "rendered_id": "render.png",
        "findings": [{
            "id": "det-visual",
            "object_id": "title",
            "domain": "geometry",
            "severity": "P1",
            "message": "title region mismatch",
            "confidence": 1.0,
            "proposed_patch": {},
        }],
    })


def test_unknown_astra_object_id_fails_closed():
    astra = DifferenceGraph.from_dict({
        "version": "1.0", "source_id": "reference.png", "rendered_id": "render.png",
        "findings": [{
            "id": "a1", "object_id": "invented", "domain": "geometry", "severity": "P1",
            "message": "move it", "confidence": 0.99, "proposed_patch": {"x": 0.2},
        }],
    })
    try:
        ingest_astra_qa(page_graph=_page(), deterministic_graph=_deterministic(), astra_graph=astra)
    except AstraIngestionError as exc:
        assert "unknown object ids" in str(exc)
    else:
        raise AssertionError("expected unknown Astra object id to fail closed")


def test_deterministic_blocker_survives_astra_merge():
    astra = DifferenceGraph.from_dict({
        "version": "1.0", "source_id": "reference.png", "rendered_id": "render.png",
        "findings": [{
            "id": "a2", "object_id": "title", "domain": "typography", "severity": "P2",
            "message": "font slightly small", "confidence": 0.95, "proposed_patch": {"font_size": 26},
        }],
    })
    result = ingest_astra_qa(page_graph=_page(), deterministic_graph=_deterministic(), astra_graph=astra)
    findings = result["merged_difference_graph"]["findings"]
    assert any(item["id"] == "det-visual" and item["severity"] == "P1" for item in findings)
    assert result["summary"]["blocking_count"] >= 1


def test_page_visual_diagnostic_does_not_block_object_repair():
    deterministic = DifferenceGraph.from_dict({
        "version": "1.0", "source_id": "reference.png", "rendered_id": "render.png",
        "findings": [{
            "id": "det-page", "object_id": "slide:1:visual", "domain": "geometry", "severity": "P1",
            "message": "page visual below threshold", "confidence": 1.0, "proposed_patch": {},
            "evidence": {"source": "dual-comparison", "kind": "pixel", "slide": 1},
        }],
    })
    astra = DifferenceGraph.from_dict({
        "version": "1.0", "source_id": "reference.png", "rendered_id": "render.png",
        "findings": [{
            "id": "a-page-fix", "object_id": "title", "domain": "geometry", "severity": "P1",
            "message": "title shifted right", "confidence": 0.97, "proposed_patch": {"x": 0.08},
        }],
    })
    result = ingest_astra_qa(page_graph=_page(), deterministic_graph=deterministic, astra_graph=astra)
    assert result["summary"]["blocking_count"] == 2
    assert result["summary"]["repair_action_count"] == 1
    assert result["summary"]["blocking_deferred"] is False
    deferred = result["repair_plan"]["deferred"]
    assert any(item.get("diagnostic_only") is True for item in deferred)


def test_low_confidence_astra_patch_is_deferred():
    astra = DifferenceGraph.from_dict({
        "version": "1.0", "source_id": "reference.png", "rendered_id": "render.png",
        "findings": [{
            "id": "a3", "object_id": "icon", "domain": "asset", "severity": "P1",
            "message": "icon style mismatch", "confidence": 0.5,
            "proposed_patch": {"regenerate": True, "generation_prompt": "simple line icon"},
        }],
    })
    result = ingest_astra_qa(page_graph=_page(), deterministic_graph=DifferenceGraph.from_dict({
        "version": "1.0", "source_id": "reference.png", "rendered_id": "render.png", "findings": []
    }), astra_graph=astra)
    assert result["summary"]["repair_action_count"] == 0
    assert result["summary"]["deferred_count"] == 1
    assert result["summary"]["blocking_deferred"] is True


def test_convergence_delta_detects_regression():
    delta = convergence_delta(
        {"pixel_fidelity_score": 0.91, "blocking_count": 1},
        {"pixel_fidelity_score": 0.88, "blocking_count": 2},
    )
    assert delta["regressed"] is True
    assert delta["pixel_fidelity_delta"] < 0
    assert delta["blocking_delta"] == 1


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Astra batch ingestion tests passed")
