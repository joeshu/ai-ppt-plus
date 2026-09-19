#!/usr/bin/env python3
"""Regression test for reference line-topology preservation."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_SCRIPTS = ROOT / "ai-ppt-editable" / "scripts"
sys.path.insert(0, str(WORKER_SCRIPTS))


def load_module():
    path = WORKER_SCRIPTS / "validate_text_topology.py"
    spec = importlib.util.spec_from_file_location("validate_text_topology", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    worker = (WORKER_SCRIPTS / "validate_text_topology.py").read_text(encoding="utf-8")
    mirror = (ROOT / "scripts" / "validate_text_topology.py").read_text(encoding="utf-8")
    assert worker == mirror
    gate = (WORKER_SCRIPTS / "text_fit_authoring_gate.py").read_text(encoding="utf-8")
    assert "audit_text_topology" in gate
    assert "topology_defect_count" in gate
    assert "strict_reference_release_required" in gate

    module = load_module()
    deck = {
        "schema": "ai-ppt-plus/layout/v3",
        "units": "px",
        "ref_width": 1000,
        "ref_height": 562,
        "slide_width_px": 1000,
        "slide_height_px": 562,
        "slide_width_in": 13.333333,
        "slide_height_in": 7.493333,
        "font_family": "Noto Sans CJK SC",
        "slides": [{"texts": [{
            "object_id": "single-line-heading",
            "x": 50, "y": 50, "w": 130, "h": 40,
            "text": "这是必须保持单行的参考标题",
            "font_size_pt": 24,
            "reference_line_count": 1,
        }]}],
    }
    with tempfile.TemporaryDirectory() as tmp:
        layout = Path(tmp) / "layout.json"
        layout.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        report = module.audit_text_topology(layout)
    assert not report["valid"]
    assert report["issues"][0]["code"] == "reference_line_topology_changed"
    print("reference text topology gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
