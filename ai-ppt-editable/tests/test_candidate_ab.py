#!/usr/bin/env python3
from copy import deepcopy

from reconstruction.candidate_ab import evaluate_candidate_ab, verify_candidate_ab_replay


def record(variant: str, *, target=0.90, mandatory=0.96, global_score=0.95, layout=0.95, pixel=0.95):
    return {
        "case_id": "fttr-case",
        "variant_id": variant,
        "accepted": True,
        "blocking_count": 0,
        "native_editability_valid": True,
        "semantic_accuracy": 1.0,
        "unauthorized_object_drift_count": 0,
        "comparison_context": {
            "source_sha256": "1" * 64,
            "reference_sha256": "2" * 64,
            "renderer": "libreoffice",
            "renderer_version": "26.2",
            "canvas": {"width": 1920, "height": 1080},
            "font_profile_hash": "3" * 64,
            "policy_version": "rf-v6",
        },
        "metrics": {
            "global_visual_similarity": global_score,
            "blurred_layout_ssim": layout,
            "pixel_fidelity_score": pixel,
            "full_slide_raster_detected": False,
            "critical_region_scores": {"target-icon": target, "locked-title": mandatory},
        },
        "generated_asset_count": 1 if variant == "v6" else 0,
        "generated_assets": ([{
            "asset_id": "asset-1",
            "target_region_id": "target-icon",
            "provider": "openai",
            "model": "image-gen",
            "prompt_sha256": "a" * 64,
            "asset_sha256": "b" * 64,
        }] if variant == "v6" else []),
        "artifacts": {"pptx": f"{variant}.pptx", "render": f"{variant}.png"},
    }


def evaluate(base, cand):
    return evaluate_candidate_ab(base, cand, target_region_ids=["target-icon"], mandatory_region_ids=["locked-title"])


def main():
    base = record("v5")
    cand = record("v6", target=0.93, mandatory=0.961, global_score=0.952, layout=0.951, pixel=0.953)
    result = evaluate(base, cand)
    assert result["accepted"] is True, result
    assert result["winner_variant"] == "v6"
    assert result["rollback_to_baseline"] is False
    assert result["provenance"]["bound"] is True
    assert verify_candidate_ab_replay(result, base, cand) is True

    mismatch = deepcopy(cand)
    mismatch["comparison_context"]["renderer_version"] = "different"
    result = evaluate(base, mismatch)
    assert result["accepted"] is False
    assert "comparison_context_mismatch" in result["reasons"]
    assert result["winner_variant"] == "v5"

    regression = record("v6", target=0.93, mandatory=0.961, global_score=0.94, layout=0.951, pixel=0.953)
    result = evaluate(base, regression)
    assert result["accepted"] is False
    assert "comparison_metric_regressed:global_visual_similarity" in result["reasons"]

    region_regression = record("v6", target=0.93, mandatory=0.94, global_score=0.952, layout=0.951, pixel=0.953)
    result = evaluate(base, region_regression)
    assert result["accepted"] is False
    assert "mandatory_region_regressed:locked-title" in result["reasons"]

    missing_provenance = deepcopy(cand)
    del missing_provenance["generated_assets"][0]["provider"]
    result = evaluate(base, missing_provenance)
    assert result["accepted"] is False
    assert any(reason.startswith("generated_asset_provenance_incomplete") for reason in result["reasons"])

    missing_target = deepcopy(cand)
    del missing_target["metrics"]["critical_region_scores"]["target-icon"]
    result = evaluate(base, missing_target)
    assert result["accepted"] is False
    assert "target_region_evidence_missing:target-icon" in result["reasons"]

    tampered = evaluate(base, cand)
    tampered["winner_variant"] = "v5"
    assert verify_candidate_ab_replay(tampered, base, cand) is False

    raster = deepcopy(cand)
    raster["metrics"]["full_slide_raster_detected"] = True
    result = evaluate(base, raster)
    assert result["accepted"] is False
    assert "candidate_full_slide_raster_detected" in result["reasons"]

    print("candidate A/B gate: ok")


if __name__ == "__main__":
    main()
