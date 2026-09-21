from __future__ import annotations

import sys
from pathlib import Path

DEV_EVALUATORS = Path(__file__).resolve().parents[1] / "evals" / "competitive"
sys.path.insert(0, str(DEV_EVALUATORS))

from beat_knight_evaluator import _absolute_floor


def candidate():
    return {
        "editability": {"formal_text_native": True, "whole_slide_picture_count": 0},
        "text": {"missing_count": 0, "overflow_count": 0},
        "object": {"blocking_count": 0},
        "icon_asset": {"independent_assets": True, "alpha_failure_count": 0},
        "blocking_count": 0,
    }


def test_competitive_floor_rejects_legacy_source_crop_fixture():
    passed, checks = _absolute_floor(candidate(), require_imagegen=True)
    assert not passed
    assert checks["imagegen_final_assets"] is False
    assert checks["alpha_centroid_evidence"] is False
    assert checks["no_contact_sheet_ancestry"] is False


def test_competitive_floor_accepts_independent_imagegen_alpha_assets():
    value = candidate()
    value["asset_provenance"] = {
        "imagegen_final_assets": True,
        "alpha_centroid_evidence": True,
        "contact_sheet_ancestry_count": 0,
    }
    passed, checks = _absolute_floor(value, require_imagegen=True)
    assert passed, checks


if __name__ == "__main__":
    test_competitive_floor_rejects_legacy_source_crop_fixture()
    test_competitive_floor_accepts_independent_imagegen_alpha_assets()
    print("Beat-Knight ImageGen provenance gate: ok")
