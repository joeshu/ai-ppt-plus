#!/usr/bin/env python3
"""Regression test for the three-round provenance and editability protocol."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    protocol = (ROOT / "references/three-round-distillation-methodology.md").read_text(encoding="utf-8")
    for phrase in (
        "Round 1", "Round 2", "Round 3", "visual-best", "editable-best",
        "source_bbox", "SHA-256", "standalone `ai-ppt-editable/scripts/run_pipeline.py`",
    ):
        assert phrase in protocol, phrase

    with tempfile.TemporaryDirectory(prefix="three-round-distillation-") as temp:
        root = Path(temp)
        source = root / "source.png"
        Image.new("RGB", (300, 200), "white").save(source)
        assets = root / "assets/panels"
        assets.mkdir(parents=True)
        for name, color in (("panel-a.png", "#D71920"), ("panel-b.png", "#0B6EBD")):
            Image.new("RGB", (120, 60), color).save(assets / name)

        panel_manifest = root / "panel-asset-manifest.json"
        panels = []
        for index, name in enumerate(("panel-a.png", "panel-b.png")):
            panel_path = assets / name
            panels.append({
                "panel_id": f"panel-{index + 1}",
                "file": f"assets/panels/{name}",
                "source_bbox": [20 + index * 140, 20, 120, 60],
                "treatment": "transparent-image",
                "formal_text_baked_in": False,
                "asset_size": [120, 60],
                "sha256": digest(panel_path),
            })
        panel_manifest.write_text(json.dumps({
            "schema": "ai-ppt-plus/panel-assets/v1",
            "status": "approved",
            "source": "source.png",
            "source_size": [300, 200],
            "source_sha256": digest(source),
            "whole_frame": False,
            "approval": {
                "reviewer": "regression",
                "approved_at": "2026-01-01T00:00:00Z",
                "revision": "fixture",
                "candidate_manifest": "layout.json",
                "candidate_manifest_sha256": "fixture",
            },
            "panels": panels,
        }, ensure_ascii=False), encoding="utf-8")

        layout = root / "layout.json"
        layout.write_text(json.dumps({
            "project_id": "three-round-fixture",
            "units": "px",
            "ref_width": 300,
            "ref_height": 200,
            "slide_width_in": 3,
            "slide_height_in": 2,
            "assets_dir": "assets/panels",
            "slides": [
                {"panels": [{"object_id": "panel-1", "file": "panel-a.png", "x": 20, "y": 20, "w": 120, "h": 60}], "texts": [{"object_id": "title-1", "text": "可编辑", "x": 10, "y": 5, "w": 100, "h": 15, "source_bbox": [10, 5, 100, 15]}]},
                {"panels": [{"object_id": "panel-2", "file": "panel-b.png", "x": 160, "y": 20, "w": 120, "h": 60}], "texts": [{"object_id": "title-2", "text": "可复用", "x": 10, "y": 5, "w": 100, "h": 15, "source_bbox": [10, 5, 100, 15]}]},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        object_manifest = root / "slide-object-manifest.json"
        built = run("scripts/build_object_manifest.py", str(layout), "--panel-manifest", str(panel_manifest), "--output", str(object_manifest))
        assert built.returncode == 0, built.stdout + built.stderr
        data = json.loads(object_manifest.read_text(encoding="utf-8"))
        objects = [obj for slide in data["slides"] for obj in slide["objects"] if obj.get("role") == "semantic-panel"]
        assert len(objects) == 2
        assert {obj["source_path"] for obj in objects} == {"assets/panels/panel-a.png", "assets/panels/panel-b.png"}
        assert all(obj.get("source_bbox") and len(obj.get("source_sha256", "")) == 64 for obj in objects)

        checked = run("scripts/validate_panel_assets.py", str(panel_manifest), "--assets-dir", str(root), "--require-approved", "--require-independent", "--expected-count", "2", "--strict")
        assert checked.returncode == 0, checked.stdout + checked.stderr
    print("three-round distillation provenance contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
