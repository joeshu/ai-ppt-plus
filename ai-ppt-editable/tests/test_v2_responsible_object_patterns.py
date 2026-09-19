#!/usr/bin/env python3
"""Regression coverage for V2 responsible-object repair patterns."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_render_repair_trace import build_trace  # noqa:E402


def main() -> int:
    layout = {
        "slides": [{
            "texts": [
                {"object_id": "main_title", "semantic_role": "title", "x": 0.35, "y": 0.02, "w": 0.30, "h": 0.08},
                {"object_id": "body_copy", "semantic_role": "body", "x": 0.10, "y": 0.30, "w": 0.25, "h": 0.20},
            ],
            "images": [
                {"object_id": "kpi_badge", "semantic_role": "icon-badge", "x": 0.72, "y": 0.58, "w": 0.08, "h": 0.12},
            ],
            "semantic_regions": [
                {"object_id": "footer-system", "semantic_role": "footer-band", "x": 0.0, "y": 0.82, "w": 1.0, "h": 0.18},
            ],
        }]
    }
    regional = {
        "foreground_weighted_score": 0.84,
        "regions": [
            {"region_id": "s1:texts:main_title", "semantic_role": "title", "score": 0.91, "bbox": [0.35,0.02,0.30,0.08], "metrics": {"layout_ssim":0.88,"pixel_fidelity":0.91}},
            {"region_id": "s1:texts:body_copy", "semantic_role": "body", "score": 0.82, "bbox": [0.10,0.30,0.25,0.20], "metrics": {"layout_ssim":0.80,"pixel_fidelity":0.84}},
            {"region_id": "s1:images:kpi_badge", "semantic_role": "icon-badge", "score": 0.93, "bbox": [0.72,0.58,0.08,0.12], "metrics": {"layout_ssim":0.94,"pixel_fidelity":0.90}},
            {"region_id": "s1:semantic_regions:footer-system", "semantic_role": "footer-band", "score": 0.89, "bbox": [0.0,0.82,1.0,0.18], "metrics": {"layout_ssim":0.87,"pixel_fidelity":0.88}, "relationship_evidence": {"contour_landmarks": [[0,0.1],[0.5,0.04],[1,0.11]], "children": {"5g-mark": [0.5,0.48]}}},
        ],
        "issues": [],
    }
    trace = build_trace(layout, regional, max_actions=10, min_actions=4, target=0.90)
    by_id = {item["object_id"]: item for item in trace["pending_actions"]}
    assert by_id["main_title"]["responsibility"] == "title-block-geometry"
    assert by_id["body_copy"]["responsibility"] == "typography-density"
    assert by_id["kpi_badge"]["responsibility"] == "composite-badge-identity"
    assert by_id["footer-system"]["responsibility"] == "anchored-visual-system"
    assert by_id["footer-system"]["relationship_evidence"]["contour_landmarks"]
    assert "baseline spacing" in " ".join(trace["policy"])
    assert "composite badges" in " ".join(trace["policy"])
    assert "parent contour landmarks" in " ".join(trace["policy"])
    print("V2 responsible-object repair patterns: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
