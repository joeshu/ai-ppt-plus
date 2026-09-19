#!/usr/bin/env python3
"""Regression test: reference charts cannot bypass reconstruction authority."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "ai-ppt-editable" / "scripts"
sys.path.insert(0, str(WORKER_DIR))


def load_module():
    path = WORKER_DIR / "validate_chart_authoring_contract.py"
    spec = importlib.util.spec_from_file_location("validate_chart_authoring_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    worker = (WORKER_DIR / "validate_chart_authoring_contract.py").read_text(encoding="utf-8")
    mirror = (ROOT / "scripts" / "validate_chart_authoring_contract.py").read_text(encoding="utf-8")
    assert worker == mirror
    gate = (WORKER_DIR / "text_fit_authoring_gate.py").read_text(encoding="utf-8")
    assert "validate_chart_authoring_contract" in gate and "chart_defect_count" in gate
    module = load_module()
    deck = {"slides": [{"charts": [{"object_id": "trend-chart", "series": [{"name": "2026", "values": [1, None]}], "categories": ["1月", "2月"]}]}]}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        layout = root / "layout.json"
        layout.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        (root / "route-decision.json").write_text(json.dumps({"route": "reference-reconstruction"}), encoding="utf-8")
        report = module.validate_chart_authoring_contract(layout, deck)
    assert not report["valid"]
    assert report["issues"][0]["code"] == "chart_reconstruction_manifest_missing"
    print("chart authoring contract gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
