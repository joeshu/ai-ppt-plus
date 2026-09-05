#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reconstruction.difference_graph import DifferenceGraph
from reconstruction.quality_gate import QualityGate
from reconstruction.quality_policy import POLICY_VERSION
from reconstruction.text_target_spec import build_text_target_spec


def empty_graph() -> DifferenceGraph:
    return DifferenceGraph.from_dict({"version": "1.0", "source_id": "source", "rendered_id": "render", "findings": []})


def main() -> int:
    gate = QualityGate()
    blocked = gate.evaluate(
        differences=empty_graph(),
        global_visual_similarity=.99,
        critical_region_scores={"title": .99},
        required_critical_regions=["title"],
        axis_scores={"layout": .99, "typography": .99},
        strict_reference_profile=True,
        editable_ratio=1.0,
        semantic_accuracy=1.0,
        full_slide_raster_detected=False,
    )
    assert not blocked.passed
    assert any("missing fidelity axis scores: asset" in item for item in blocked.failures)

    passed = gate.evaluate(
        differences=empty_graph(),
        global_visual_similarity=.99,
        critical_region_scores={"title": .99},
        required_critical_regions=["title"],
        axis_scores={"layout": .99, "typography": .99, "asset": .99},
        strict_reference_profile=True,
        editable_ratio=1.0,
        semantic_accuracy=1.0,
        full_slide_raster_detected=False,
    )
    assert passed.passed, passed.failures
    assert passed.metrics["policy_version"] == POLICY_VERSION

    with tempfile.TemporaryDirectory(prefix="text-target-spec-") as folder:
        image = Path(folder) / "source.png"
        Image.new("RGB", (1600, 900), "white").save(image)
        spec = build_text_target_spec(image, [{
            "object_id": "headline",
            "text": "存量用户价值提升 2026",
            "bbox_px": [160, 90, 960, 120],
            "baselines_px": [165],
            "line_count": 1,
            "font_candidates": ["Noto Sans SC", "Microsoft YaHei"],
            "estimated_font_size_pt": 30,
            "estimated_line_spacing": 1.0,
            "runs": [
                {"text": "存量用户", "bold": True},
                {"text": "价值提升 2026", "color": "D71920"},
            ],
            "confidence": .97,
        }])
        target = spec["targets"][0]
        assert target["measurement_kind"] == "pdf-text-bounds"
        assert target["line_count"] == 1
        assert target["text"] == "存量用户价值提升 2026"
        assert target["font_candidates"][0] == "Noto Sans SC"
        assert abs(target["ink_bbox"][0] - .1) < 1e-9
        assert abs(target["ink_bbox"][1] - .1) < 1e-9
        assert spec["source_sha256"]

    print(json.dumps({"policy": POLICY_VERSION, "status": "ok"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
