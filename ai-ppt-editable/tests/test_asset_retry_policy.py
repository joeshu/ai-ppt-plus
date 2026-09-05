from __future__ import annotations

from reconstruction.asset_retry_policy import (
    AssetRetryPolicy,
    categories_from_issue_codes,
    classify_reasons,
    next_retry_request,
    strengthen_prompt,
)


def test_legacy_reason_classification_remains_diagnostic_only():
    categories = classify_reasons(["silhouette differs and gradient color flow is wrong"])
    assert "silhouette" in categories
    assert "color" in categories


def test_issue_codes_drive_prompt_strengthening():
    quality = {
        "score": 0.75,
        "structure_score": 0.68,
        "style_score": 0.80,
        "confidence": 0.96,
        "issue_codes": ["silhouette_mismatch", "gradient_flow_mismatch"],
        "reasons": ["arbitrary prose should remain evidence only"],
    }
    categories = categories_from_issue_codes(quality["issue_codes"])
    assert "silhouette" in categories
    assert "color" in categories
    prompt = strengthen_prompt("match source icon", quality, attempt=2)
    assert "Native regeneration attempt 2" in prompt
    assert "silhouette_mismatch" in prompt
    assert "gradient_flow_mismatch" in prompt
    assert "arbitrary prose" not in prompt


def test_retry_is_bounded_to_three_native_attempts():
    request = {
        "object_id": "icon",
        "generation_prompt": "match source icon",
        "background_mode": "transparent",
        "preserve_geometry": {"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.1},
    }
    quality = {
        "score": 0.70,
        "structure_score": 0.65,
        "style_score": 0.82,
        "confidence": 0.95,
        "issue_codes": ["silhouette_mismatch"],
        "reasons": ["structure differs"],
    }
    retry = next_retry_request(request, quality, previous_attempts=1, policy=AssetRetryPolicy(3))
    assert retry["status"] == "retry-native-generation"
    assert retry["attempt"] == 2
    assert retry["preserve_geometry"] == request["preserve_geometry"]
    assert retry["quality_failure"]["issue_codes"] == ["silhouette_mismatch"]

    retry3 = next_retry_request(request, quality, previous_attempts=2, policy=AssetRetryPolicy(3))
    assert retry3["status"] == "retry-native-generation"
    assert retry3["attempt"] == 3

    stop = next_retry_request(request, quality, previous_attempts=3, policy=AssetRetryPolicy(3))
    assert stop["status"] == "user-choice-required"
    assert stop["choices"] == ["continue-native-generation", "crop-matting-fallback"]


def test_free_form_reasons_cannot_change_retry_directives():
    quality_a = {
        "issue_codes": ["style_mismatch"],
        "reasons": ["silhouette gradient composition all wrong"],
    }
    quality_b = {
        "issue_codes": ["style_mismatch"],
        "reasons": ["completely different wording"],
    }
    prompt_a = strengthen_prompt("match asset", quality_a, attempt=2)
    prompt_b = strengthen_prompt("match asset", quality_b, attempt=2)
    assert prompt_a == prompt_b
    assert "visual style" in prompt_a


def test_retry_policy_never_automatically_selects_crop_fallback():
    request = {"object_id": "art", "generation_prompt": "match artwork"}
    quality = {"issue_codes": ["composition_mismatch"], "reasons": ["composition differs"]}
    result = next_retry_request(request, quality, previous_attempts=3)
    assert result["status"] == "user-choice-required"
    assert "selected_choice" not in result


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Asset retry policy tests passed")
