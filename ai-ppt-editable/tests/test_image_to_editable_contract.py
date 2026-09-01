#!/usr/bin/env python3
"""Regression tests for the strict raster/text boundary."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(layout: dict, objects: dict, panels: dict | None) -> tuple[int, dict]:
    with tempfile.TemporaryDirectory(prefix="image-to-editable-contract-") as temp:
        root = Path(temp)
        layout_path = root / "layout.json"
        object_path = root / "slide-object-manifest.json"
        panel_path = root / "panel-asset-manifest.json"
        report_path = root / "report.json"
        layout_path.write_text(json.dumps(layout, ensure_ascii=False), encoding="utf-8")
        object_path.write_text(json.dumps(objects, ensure_ascii=False), encoding="utf-8")
        if panels is not None:
            panel_path.write_text(json.dumps(panels, ensure_ascii=False), encoding="utf-8")
        command = [
            sys.executable,
            "scripts/validate_image_to_editable_contract.py",
            "--layout", str(layout_path),
            "--object-manifest", str(object_path),
            "--report", str(report_path),
            "--strict",
        ]
        if panels is not None:
            command.extend(["--panel-manifest", str(panel_path)])
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        return result.returncode, json.loads(report_path.read_text(encoding="utf-8"))


def fixtures() -> tuple[dict, dict, dict]:
    audit = {"status": "verified-excluded", "method": "human+pixel-review", "reviewed_at": "2026-09-01T00:00:00Z", "text_layer_ids": ["body-1"]}
    layout = {
        "project_id": "contract-fixture",
        "slide_width_in": 13.333333,
        "slide_height_in": 7.5,
        "slides": [{"panels": [{"object_id": "panel-1", "file": "panel.png"}], "texts": [{"object_id": "body-1", "text": "可编辑正文"}]}],
    }
    objects = {"schema": "ai-ppt-plus/slide-object-manifest/v1", "slides": [{"slide_no": 1, "objects": [
        {"object_id": "panel-1", "role": "semantic-panel", "object_type": "traceable_static_graphic", "contains_formal_content": False, "raster_text_audit": audit},
        {"object_id": "body-1", "role": "formal-text", "object_type": "editable_text", "text_spec": {"content": "可编辑正文"}},
    ]}]}
    panels = {"schema": "ai-ppt-plus/panel-assets/v1", "panels": [{"panel_id": "panel-1", "file": "panel.png", "formal_text_baked_in": False, "raster_text_audit": audit}]}
    return layout, objects, panels


def main() -> int:
    layout, objects, panels = fixtures()
    code, report = run(layout, objects, panels)
    assert code == 0, report
    assert report["valid"] is True and report["formal_text_object_count"] == 1, report

    missing = copy.deepcopy(panels)
    missing["panels"][0].pop("raster_text_audit")
    missing_objects = copy.deepcopy(objects)
    missing_objects["slides"][0]["objects"][0].pop("raster_text_audit")
    code, report = run(layout, missing_objects, missing)
    assert code != 0 and any(item["code"] == "raster_text_audit_missing" for item in report["issues"]), report

    baked = copy.deepcopy(panels)
    baked["panels"][0]["formal_text_baked_in"] = True
    code, report = run(layout, objects, baked)
    assert code != 0 and any(item["code"] == "formal_text_baked_in" for item in report["issues"]), report

    flattened = copy.deepcopy(objects)
    flattened["slides"][0]["objects"].append({"object_id": "slide-shot", "role": "flattened_full_slide", "object_type": "flattened_full_slide"})
    code, report = run(layout, flattened, panels)
    assert code != 0 and any(item["code"] == "flattened_full_slide_forbidden" for item in report["issues"]), report

    protocol = (ROOT / "references/image-to-editable-ppt-contract.md").read_text(encoding="utf-8")
    assert "所有正式可见文字" in protocol and "raster_text_audit" in protocol and "不是重新设计" in protocol
    print("strict image-to-editable raster/text contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
