#!/usr/bin/env python3
"""Root package exposes the same safe ImageGen batch planner as its worker."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_imagegen_asset_jobs import plan


def main() -> int:
    def item(asset_id: str) -> dict:
        return {
            "asset_id": asset_id, "asset_class": "icon", "route": "imagegen_asset",
            "source_bbox": [0.1, 0.1, 0.1, 0.1], "aspect_ratio": 1,
            "prompt": asset_id,
            "asset_contract": {
                "schema": "ai-ppt-plus/asset-identity-contract/v1",
                "semantic_identity": {"subject": asset_id},
                "alpha": {"required": True},
            },
        }
    result = plan({"execution_profile": "strict", "source": {"sha256": "c" * 64}, "assets": [item(f"icon-{index}") for index in range(8)]})
    assert result["schema"] == "ai-ppt-plus/imagegen-asset-jobs/v6"
    assert result["native_tool"] == "image_gen.imagegen"
    assert result["native_tool_receipt_required"] is True
    assert result["batch_count"] == 3
    assert result["estimated_uncached_imagegen_calls"] == 3
    assert [len(batch["cells"]) for batch in result["generation_batches"]] == [3, 3, 2]
    assert all(batch["max_assets"] == 3 for batch in result["generation_batches"])
    print("root ImageGen batch planning: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
