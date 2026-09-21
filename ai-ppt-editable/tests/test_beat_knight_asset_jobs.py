#!/usr/bin/env python3
"""Lock the Beat-Knight rerun to deterministic independent ImageGen jobs with B3 contracts."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_imagegen_asset_jobs import plan


def test_beat_knight_asset_jobs_are_reproducible_and_independent():
    source_path = ROOT / "evals" / "beat-knight" / "降套管控-1536x864-imagegen-assets.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    generated = plan(source)
    repeated = plan(copy.deepcopy(source))

    assert generated == repeated
    assert generated["schema"] == "ai-ppt-plus/imagegen-asset-jobs/v6"
    assert generated["execution_profile"] == "fast"
    assert generated["job_count"] == 3
    assert generated["batch_count"] == 0
    assert generated["estimated_uncached_imagegen_calls"] == 3
    assert [job["asset_id"] for job in generated["jobs"]] == [
        "brand-logo-lockup",
        "service-calligraphy-lockup",
        "bottom-brand-band",
    ]
    assert len({job["cache_key"] for job in generated["jobs"]}) == 3
    for job in generated["jobs"]:
        assert job["route"] == "imagegen_asset"
        assert job["contract_complete"] is True
        assert job["asset_contract"]["schema"] == "ai-ppt-plus/asset-identity-contract/v1"
        assert job["qa"]["independent_asset"] is True
        assert job["qa"]["contact_sheet_forbidden"] is True
        assert job["qa"]["transparent_rgba"] is True
        assert job["qa"]["identity_contract_required"] is True
        assert job["qa"]["semantic_identity_compare"] is True
        assert job["qa"]["contour_identity_compare"] is True
        assert job["qa"]["color_role_compare"] is True
        assert job["request"]["placement_mode"] == "alpha-centroid-fit"
        assert "Asset identity/color contract:" in job["request"]["generation_prompt"]
        assert job["retry_scope"] == "asset_only"
        assert job["retry"]["automatic_source_reuse"] is False
        assert job["retry"]["placement_only_consumes_generation_attempt"] is False
        assert job["retry"]["identity_or_color_requires_regeneration"] is True
        assert job["retry"]["max_retries"] == 1
        assert "asset_identity_color_pass" in job["cache"]["reuse_requires"]
        assert job["source_reuse"] == "forbidden_without_user_approved_fallback"


if __name__ == "__main__":
    test_beat_knight_asset_jobs_are_reproducible_and_independent()
    print("Beat-Knight ImageGen asset identity jobs: ok")
