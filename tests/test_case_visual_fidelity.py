#!/usr/bin/env python3
"""Regression tests for the reference-reconstruction visual gate."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-ppt-editable" / "scripts"))

from validate_case_visual_fidelity import validate_case_visual_fidelity


def sample_case() -> dict:
    return {
        "case_id": "fidelity-test-01",
        "formal_text": ["标题", "节点A", "节点B"],
        "data": {"metric": "86%"},
    }


def sample_text_manifest() -> dict:
    return {
        "schema": "ai-ppt-plus/text-layout-manifest/v1",
        "slides": [{
            "slide_no": 1,
            "text_specs": [
                {
                    "object_id": f"text-{index}",
                    "content": value,
                    "source_bbox": [0.1, index * 0.1, 0.4, 0.05],
                    "style": {"font_family": "Noto Sans CJK SC", "size_pt": 18},
                }
                for index, value in enumerate(["标题", "节点A", "节点B"])
            ],
        }],
    }


def good_payload() -> dict:
    return {
        "visual": {
            "valid": True,
            "metrics": {"global_ssim": 0.52, "blurred_layout_ssim": 0.72, "pixel_fidelity_score": 0.9},
            "issues": [],
        },
        "reference_sha256": "a" * 64,
        "candidate_origin": "reference-reconstruction",
        "reference_binding": {"bound": True, "reference_sha256": "a" * 64},
        "asset_evidence": {"imagegen_assets_manifest": "imagegen-assets-manifest.json", "independent_asset_count": 2, "asset_ids": ["icon-1", "illustration-1"], "all_assets_text_free": True},
        "typography_evidence": {"source_bbox_count": 3, "font_manifest": "fonts/font-manifest.json"},
        "text_manifest": sample_text_manifest(),
    }


def main() -> int:
    case = sample_case()
    good = good_payload()
    passed = validate_case_visual_fidelity(
        case,
        visual=good["visual"],
        reference_sha256=good["reference_sha256"],
        candidate_origin=good["candidate_origin"],
        reference_binding=good["reference_binding"],
        asset_evidence=good["asset_evidence"],
        typography_evidence=good["typography_evidence"],
        text_manifest=good["text_manifest"],
    )
    assert passed["valid"], passed

    blocked = dict(good)
    blocked["visual"] = {"valid": True, "metrics": {"global_ssim": 0.04, "blurred_layout_ssim": 0.12, "pixel_fidelity_score": 0.7}, "issues": []}
    blocked["candidate_origin"] = "synthetic-contract-control"
    blocked["reference_binding"] = {"bound": False, "reference_sha256": good["reference_sha256"]}
    blocked_result = validate_case_visual_fidelity(
        case,
        visual=blocked["visual"],
        reference_sha256=blocked["reference_sha256"],
        candidate_origin=blocked["candidate_origin"],
        reference_binding=blocked["reference_binding"],
        asset_evidence=blocked["asset_evidence"],
        typography_evidence=blocked["typography_evidence"],
        text_manifest=blocked["text_manifest"],
    )
    codes = {item["code"] for item in blocked_result["issues"]}
    assert not blocked_result["valid"], blocked_result
    assert "candidate_origin_not_reference_reconstruction" in codes, codes
    assert "reference_binding_missing" in codes, codes
    assert "visual_metric_below_threshold" in codes, codes
    print("case visual fidelity gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
