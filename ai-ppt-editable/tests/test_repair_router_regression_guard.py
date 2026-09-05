#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reconstruction.difference_graph import DifferenceGraph
from reconstruction.object_drift_guard import compare_object_drift
from reconstruction.repair_router import RepairRouter


def main() -> int:
    graph = DifferenceGraph.from_dict({
        "version": "1.0",
        "source_id": "source",
        "rendered_id": "render",
        "findings": [{
            "id": "hierarchy:group-1",
            "object_id": "group-1",
            "domain": "hierarchy",
            "severity": "P1",
            "message": "group membership differs from reference",
            "confidence": .99,
            "proposed_patch": {"group_children": ["a", "b"]},
        }],
    })
    plan = RepairRouter().build_plan(graph)
    assert len(plan.actions) == 1
    assert plan.actions[0].engine == "semantic_repair"
    assert plan.actions[0].patch == {"group_children": ["a", "b"]}

    before = {"slides": [{"texts": [
        {"object_id": "title", "x": .1, "y": .1, "w": .4, "h": .1, "text": "A"},
        {"object_id": "body", "x": .1, "y": .3, "w": .5, "h": .2, "text": "B"},
    ]}]}
    after = {"slides": [{"texts": [
        {"object_id": "title", "x": .12, "y": .1, "w": .4, "h": .1, "text": "A"},
        {"object_id": "body", "x": .1, "y": .3, "w": .5, "h": .2, "text": "CHANGED"},
    ]}]}
    report = compare_object_drift(before, after, allowed_object_ids={"title"})
    assert report["valid"] is False
    assert report["unauthorized_drift_count"] == 1
    assert report["drift"][0]["object_id"] == "body"
    print("repair routing and regression guard: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
