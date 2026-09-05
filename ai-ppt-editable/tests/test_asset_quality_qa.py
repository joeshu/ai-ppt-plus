from __future__ import annotations

from reconstruction.asset_quality_qa import (
    AssetQualityThresholds,
    build_asset_quality_request,
    parse_asset_quality_response,
)


def test_asset_quality_request_is_object_local():
    req = build_asset_quality_request(
        object_id="icon-1",
        source_region_id="reference#region:icon-1",
        generated_asset_id="generated/icon-1.png",
        asset_kind="icon",
        generation_prompt="simple white line icon",
        background_mode="transparent",
    )
    assert req.task == "asset-visual-qa"
    assert req.payload["object_id"] == "icon-1"
    assert req.payload["source_region_id"].endswith("icon-1")


def test_asset_quality_passes_only_above_all_thresholds():
    result = parse_asset_quality_response({
        "object_id": "icon-1",
        "approved": True,
        "score": 0.93,
        "structure_score": 0.94,
        "style_score": 0.89,
        "reasons": [],
        "retry_native_generation": False,
    }, expected_object_id="icon-1")
    assert result["approved"] is True


def test_model_approval_cannot_override_structure_threshold():
    result = parse_asset_quality_response({
        "object_id": "icon-1",
        "approved": True,
        "score": 0.95,
        "structure_score": 0.72,
        "style_score": 0.95,
        "reasons": ["silhouette differs"],
    }, expected_object_id="icon-1")
    assert result["approved"] is False
    assert result["retry_native_generation"] is True


def test_object_id_mismatch_fails_closed():
    try:
        parse_asset_quality_response({
            "object_id": "other",
            "approved": True,
            "score": 1.0,
            "structure_score": 1.0,
            "style_score": 1.0,
            "reasons": [],
        }, expected_object_id="icon-1")
    except ValueError as exc:
        assert "object_id mismatch" in str(exc)
    else:
        raise AssertionError("expected object mismatch failure")


def test_custom_thresholds_are_enforced():
    result = parse_asset_quality_response({
        "object_id": "art-1",
        "approved": True,
        "score": 0.94,
        "structure_score": 0.94,
        "style_score": 0.91,
        "reasons": [],
    }, expected_object_id="art-1", thresholds=AssetQualityThresholds(min_score=0.95, min_structure_score=0.90, min_style_score=0.90))
    assert result["approved"] is False


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Asset quality QA tests passed")
