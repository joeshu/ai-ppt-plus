from __future__ import annotations

from reconstruction.asset_retry_policy import AssetRetryPolicy, classify_reasons, next_retry_request, strengthen_prompt


def test_failure_reason_classification_and_prompt_strengthening():
    quality = {
        "score": 0.75,
        "structure_score": 0.68,
        "style_score": 0.80,
        "reasons": ["silhouette differs and gradient color flow is wrong"],
    }
    categories = classify_reasons(quality["reasons"])
    assert "silhouette" in categories
    assert "color" in categories
    prompt = strengthen_prompt("match source icon", quality, attempt=2)
    assert "Native regeneration attempt 2" in prompt
    assert "silhouette" in prompt.casefold()
    assert "gradient" in prompt.casefold()


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
        "reasons": ["structure differs"],
    }
    retry = next_retry_request(request, quality, previous_attempts=1, policy=AssetRetryPolicy(3))
    assert retry["status"] == "retry-native-generation"
    assert retry["attempt"] == 2
    assert retry["preserve_geometry"] == request["preserve_geometry"]

    retry3 = next_retry_request(request, quality, previous_attempts=2, policy=AssetRetryPolicy(3))
    assert retry3["status"] == "retry-native-generation"
    assert retry3["attempt"] == 3

    stop = next_retry_request(request, quality, previous_attempts=3, policy=AssetRetryPolicy(3))
    assert stop["status"] == "user-choice-required"
    assert stop["choices"] == ["continue-native-generation", "crop-matting-fallback"]


def test_retry_policy_never_automatically_selects_crop_fallback():
    request = {"object_id": "art", "generation_prompt": "match artwork"}
    quality = {"reasons": ["composition differs"]}
    result = next_retry_request(request, quality, previous_attempts=3)
    assert result["status"] == "user-choice-required"
    assert "selected_choice" not in result


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Asset retry policy tests passed")
