from __future__ import annotations

from reconstruction.asset_quality_qa import (
    AssetQualityThresholds,
    build_asset_quality_request,
    parse_asset_quality_response,
)


def base_response(**overrides):
    payload = {
        "object_id": "icon-1",
        "approved": True,
        "score": 0.93,
        "structure_score": 0.94,
        "style_score": 0.89,
        "confidence": 0.95,
        "issue_codes": [],
        "reasons": [],
        "retry_native_generation": False,
    }
    payload.update(overrides)
    return payload


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
    assert req.payload["output_contract"] == "asset-quality-response/v2"
    assert "silhouette_mismatch" in req.payload["allowed_issue_codes"]


def test_asset_quality_passes_only_above_all_thresholds():
    result = parse_asset_quality_response(base_response(), expected_object_id="icon-1")
    assert result["approved"] is True
    assert result["confidence"] == 0.95


def test_model_approval_cannot_override_structure_threshold():
    result = parse_asset_quality_response(base_response(
        structure_score=0.72,
        issue_codes=["silhouette_mismatch"],
        reasons=["silhouette differs"],
        retry_native_generation=True,
    ), expected_object_id="icon-1")
    assert result["approved"] is False
    assert result["retry_native_generation"] is True


def test_low_confidence_fails_closed_without_auto_retry():
    result = parse_asset_quality_response(base_response(
        confidence=0.60,
        retry_native_generation=True,
    ), expected_object_id="icon-1")
    assert result["approved"] is False
    assert result["retry_native_generation"] is False


def test_issue_code_blocks_approval_even_with_high_scores():
    result = parse_asset_quality_response(base_response(
        issue_codes=["style_mismatch"],
        reasons=["style still differs"],
    ), expected_object_id="icon-1")
    assert result["approved"] is False


def test_unknown_issue_code_fails_closed():
    try:
        parse_asset_quality_response(base_response(issue_codes=["free_form_unknown"]), expected_object_id="icon-1")
    except ValueError as exc:
        assert "unsupported values" in str(exc)
    else:
        raise AssertionError("expected unsupported issue code failure")


def test_object_id_mismatch_fails_closed():
    try:
        parse_asset_quality_response(base_response(object_id="other"), expected_object_id="icon-1")
    except ValueError as exc:
        assert "object_id mismatch" in str(exc)
    else:
        raise AssertionError("expected object mismatch failure")


def test_custom_thresholds_are_enforced():
    result = parse_asset_quality_response(base_response(
        object_id="art-1",
        score=0.94,
        structure_score=0.94,
        style_score=0.91,
        confidence=0.96,
    ), expected_object_id="art-1", thresholds=AssetQualityThresholds(
        min_score=0.95,
        min_structure_score=0.90,
        min_style_score=0.90,
        min_confidence=0.90,
    ))
    assert result["approved"] is False


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Asset quality QA tests passed")
