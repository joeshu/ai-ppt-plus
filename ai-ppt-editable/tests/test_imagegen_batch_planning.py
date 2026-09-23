#!/usr/bin/env python3
"""Safe ImageGen batching reduces external calls without weakening asset QA."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_imagegen_asset_jobs import plan


def contract(subject: str) -> dict:
    return {
        "schema": "ai-ppt-plus/asset-identity-contract/v1",
        "semantic_identity": {"subject": subject, "must_preserve": [subject], "forbidden_substitutions": ["generic symbol"]},
        "contour_traits": ["simple centered pictogram"],
        "color_roles": [{"role": "accent", "hex": "#E60012"}],
        "alpha": {"required": True},
    }


def asset(asset_id: str, asset_class: str = "icon", ratio: float = 1.0) -> dict:
    return {
        "asset_id": asset_id,
        "asset_class": asset_class,
        "route": "imagegen_asset",
        "source_bbox": [0.1, 0.1, 0.1, 0.1],
        "aspect_ratio": ratio,
        "alpha_required": True,
        "prompt": f"recreate {asset_id}",
        "asset_contract": contract(asset_id),
    }


def test_fast_batches_only_compatible_simple_icons():
    data = {
        "execution_profile": "fast",
        "source": {"sha256": "a" * 64},
        "assets": [asset(f"icon-{index}") for index in range(4)] + [asset("brand", "brand_lockup", 1.5)],
    }
    result = plan(data)
    assert result["schema"] == "ai-ppt-plus/imagegen-asset-jobs/v6"
    assert result["native_tool"] == "image_gen.imagegen"
    assert result["native_tool_receipt_required"] is True
    assert result["job_count"] == 5
    assert result["batch_count"] == 1
    assert result["estimated_uncached_imagegen_calls"] == 2
    batch = result["generation_batches"][0]
    assert len(batch["cells"]) == 4
    assert batch["deliver_intermediate"] is False
    assert batch["slice_required"] is True
    assert batch["independent_asset_validation_required"] is True
    brand = next(job for job in result["jobs"] if job["asset_id"] == "brand")
    assert "generation_batch_id" not in brand
    for job in result["jobs"][:4]:
        assert job["generation_batch_id"] == batch["batch_id"]
        assert job["batch_delivery"] == "independent_alpha_slice_required"
        assert job["qa"]["contact_sheet_forbidden"] is True
        assert job["request"]["native_tool"] == "image_gen.imagegen"


def test_explicit_independent_policy_disables_batching():
    data = {
        "execution_profile": "fast",
        "policy": {"independent_generation_per_asset": True},
        "source": {"sha256": "b" * 64},
        "assets": [asset("one"), asset("two")],
    }
    result = plan(data)
    assert result["batch_count"] == 0
    assert result["estimated_uncached_imagegen_calls"] == 2


def test_strict_uses_smaller_batch_for_safer_comparison():
    data = {
        "execution_profile": "strict",
        "source": {"sha256": "d" * 64},
        "assets": [asset(f"strict-{index}") for index in range(8)],
    }
    result = plan(data)
    assert result["batch_count"] == 3
    assert [len(batch["cells"]) for batch in result["generation_batches"]] == [3, 3, 2]
    assert result["estimated_uncached_imagegen_calls"] == 3
    assert all(batch["max_assets"] == 3 for batch in result["generation_batches"])


def test_fast_caps_large_deck_batches_and_keeps_remainder_independent():
    data = {
        "execution_profile": "fast",
        "source": {"sha256": "e" * 64},
        "assets": [asset(f"fast-{index}") for index in range(9)],
    }
    result = plan(data)
    assert [len(batch["cells"]) for batch in result["generation_batches"]] == [4, 4]
    assert all(batch["max_assets"] == 4 for batch in result["generation_batches"])
    assert result["estimated_uncached_imagegen_calls"] == 3
    assert sum(len(batch["cells"]) for batch in result["generation_batches"]) == 8
    assert sum("generation_batch_id" not in job for job in result["jobs"]) == 1


if __name__ == "__main__":
    test_fast_batches_only_compatible_simple_icons()
    test_explicit_independent_policy_disables_batching()
    test_strict_uses_smaller_batch_for_safer_comparison()
    test_fast_caps_large_deck_batches_and_keeps_remainder_independent()
    print("ImageGen safe batch planning: ok")
