#!/usr/bin/env python3
"""Regression test for PageGraph -> final brand asset coverage."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "ai-ppt-editable" / "scripts" / "validate_brand_asset_coverage.py"
MIRROR = ROOT / "scripts" / "validate_brand_asset_coverage.py"
ICON_WORKER = ROOT / "ai-ppt-editable" / "scripts" / "validate_icon_assets.py"
ICON_MIRROR = ROOT / "scripts" / "validate_icon_assets.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_brand_asset_coverage", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def run_icon_gate(manifest: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ICON_WORKER), str(manifest)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def main() -> int:
    assert WORKER.read_text(encoding="utf-8") == MIRROR.read_text(encoding="utf-8")
    assert ICON_WORKER.read_text(encoding="utf-8") == ICON_MIRROR.read_text(encoding="utf-8")
    gate = (ROOT / "ai-ppt-editable" / "scripts" / "text_fit_authoring_gate.py").read_text(encoding="utf-8")
    assert "validate_brand_coverage" in gate and "brand_defect_count" in gate
    module = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page-graph.json").write_text(json.dumps({"nodes": [{"id": "brand-lockup", "type": "image", "role": "brand_lockup"}]}), encoding="utf-8")
        (root / "imagegen-assets-manifest.json").write_text(json.dumps({"assets": [{"asset_id": "brand-lockup", "asset_class": "brand_lockup", "independent_asset": True, "whole_asset_contract": False, "split_status": "component_split", "provenance_mode": "source_reuse"}]}), encoding="utf-8")
        report = module.validate_brand_coverage(root)
    codes = {item["code"] for item in report["issues"]}
    assert not report["valid"]
    assert "brand_lockup_whole_asset_contract_missing" in codes
    assert "brand_lockup_illegally_split" in codes
    assert "brand_asset_requires_native_imagegen" in codes

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "frame.png").write_bytes(b"frame")
        (root / "contact.png").write_bytes(b"contact")
        base = {
            "schema": "ai-ppt-plus/icon-assets/v1",
            "source_vs_frame_review": "pass",
            "frame_asset_ids": ["brand-lockup"],
            "icon_asset_ids": [],
            "frame_preview": "frame.png",
            "contact_sheet": "contact.png",
            "assets": [{
                "asset_id": "brand-lockup",
                "role": "brand_lockup",
                "source_ref": "assets/generated/brand.png",
                "source_bbox": {"x": 0, "y": 0, "w": 100, "h": 40},
                "extraction_method": "native-imagegen",
                "frame_exclusion": "pass",
                "editability_level": "L2",
                "replaceable": True,
                "asset_path": "native:assets/brand.png",
                "alpha_quality": "pass",
                "edge_touch": False,
                "split_status": "not-applicable",
                "duplicate_guard": "pass",
                "anchor": "header-left",
                "review_status": "pass",
                "prompt_ref": "prompt.txt",
                "provenance_mode": "imagegen",
                "generated_source": "assets/generated/brand.png",
                "copied_to": "assets/brand.png",
                "prompt_file": "prompt.txt",
                "backend": "image_gen.imagegen",
                "independent_asset": True,
                "whole_asset_contract": True,
            }],
        }
        manifest = root / "icon-asset-manifest.json"
        manifest.write_text(json.dumps(base), encoding="utf-8")
        assert run_icon_gate(manifest)["valid"]
        base["assets"][0]["extraction_method"] = "approved-source-asset"
        base["assets"][0]["provenance_mode"] = "source_reuse"
        manifest.write_text(json.dumps(base), encoding="utf-8")
        rejected = run_icon_gate(manifest)
        rejected_codes = {item["code"] for item in rejected["issues"]}
        assert not rejected["valid"]
        assert "brand_asset_requires_native_imagegen" in rejected_codes
        assert "brand_asset_provenance_not_imagegen" in rejected_codes
    print("brand asset coverage gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
