#!/usr/bin/env python3
"""Lock the post-alpha Beat-Knight rerun to three independent ImageGen jobs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_imagegen_asset_jobs import plan


def test_beat_knight_asset_jobs_are_reproducible_and_independent():
    source_path = ROOT / "evals" / "beat-knight" / "降套管控-1536x864-imagegen-assets.json"
    frozen_path = ROOT / "evals" / "beat-knight" / "降套管控-1536x864-imagegen-jobs.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    generated = plan(source)

    assert generated == frozen
    assert generated["job_count"] == 3
    assert [job["asset_id"] for job in generated["jobs"]] == [
        "brand-logo-lockup",
        "service-calligraphy-lockup",
        "bottom-brand-band",
    ]
    assert len({job["cache_key"] for job in generated["jobs"]}) == 3
    for job in generated["jobs"]:
        assert job["route"] == "imagegen_asset"
        assert job["qa"]["independent_asset"] is True
        assert job["qa"]["contact_sheet_forbidden"] is True
        assert job["qa"]["transparent_rgba"] is True
        assert job["request"]["placement_mode"] == "alpha-centroid-fit"
        assert job["retry_scope"] == "asset_only"
        assert job["retry"]["automatic_source_reuse"] is False
        assert job["source_reuse"] == "forbidden_without_user_approved_fallback"


if __name__ == "__main__":
    test_beat_knight_asset_jobs_are_reproducible_and_independent()
    print("Beat-Knight ImageGen asset jobs: ok")
