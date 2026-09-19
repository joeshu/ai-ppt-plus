#!/usr/bin/env python3
"""Regression test for PageGraph -> final brand asset coverage."""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "ai-ppt-editable" / "scripts" / "validate_brand_asset_coverage.py"
MIRROR = ROOT / "scripts" / "validate_brand_asset_coverage.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_brand_asset_coverage", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    assert WORKER.read_text(encoding="utf-8") == MIRROR.read_text(encoding="utf-8")
    gate = (ROOT / "ai-ppt-editable" / "scripts" / "text_fit_authoring_gate.py").read_text(encoding="utf-8")
    assert "validate_brand_coverage" in gate and "brand_defect_count" in gate
    module = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page-graph.json").write_text(json.dumps({"nodes": [{"id": "brand-lockup", "type": "image", "role": "brand_lockup"}]}), encoding="utf-8")
        (root / "imagegen-assets-manifest.json").write_text(json.dumps({"assets": [{"asset_id": "brand-lockup", "asset_class": "brand_lockup", "independent_asset": True, "whole_asset_contract": False, "split_status": "component_split"}]}), encoding="utf-8")
        report = module.validate_brand_coverage(root)
    codes = {item["code"] for item in report["issues"]}
    assert not report["valid"]
    assert "brand_lockup_whole_asset_contract_missing" in codes
    assert "brand_lockup_illegally_split" in codes
    print("brand asset coverage gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
