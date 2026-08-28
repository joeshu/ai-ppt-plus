#!/usr/bin/env python3
"""Regression tests for the unified manifest registry."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "manifest_registry.py"


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=ROOT, capture_output=True, text=True, check=False)


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        deck = root / "deck.pptx"; deck.write_bytes(b"fake-pptx")
        slide = root / "slide-manifest.json"; write(slide, {"slides": [{"slide_no": 1, "slide_id": "S01", "asset_ids": ["panel-01"]}]})
        objects = root / "slide-object-manifest.json"; write(objects, {"slides": [{"slide_no": 1, "objects": [{"object_id": "panel-01", "role": "semantic-panel", "object_type": "traceable_static_graphic", "editability_level": "L3", "independent": True}, {"object_id": "title", "object_type": "editable_text", "editability_level": "L1", "runs": [{"text": "标题"}]}]}]})
        layout = root / "layout.json"; write(layout, {"slides": [{"slide_no": 1, "regions": [{"region_id": "panel-01", "bbox": [0, 0, 1, 1], "independent": True}]}]})
        assets = root / "panel-asset-manifest.json"; write(assets, {"panels": [{"panel_id": "panel-01", "role": "semantic-panel", "path": "panel.png"}]})
        report = root / "report-index.json"; write(report, {"reports": [{"report_type": "qa", "path": "qa.json", "required": True}]}); write(root / "qa.json", {"valid": True})
        registry = root / "manifest-registry.json"
        built = run("build", "--output", registry, "--project-id", "demo", "--deck", deck, "--slide-manifest", slide, "--object-manifest", objects, "--layout", layout, "--asset-manifest", assets, "--report-index", report)
        assert built.returncode == 0, built.stderr
        data = json.loads(registry.read_text(encoding="utf-8"))
        assert data["schema"] == "ai-ppt-plus/manifest-registry/v1" and data["slides"][0]["regions"][0]["region_id"] == "panel-01"
        validation = root / "validation.json"
        checked = run("validate", registry, "--deck", deck, "--report", validation, "--require-gates")
        assert checked.returncode == 0, checked.stdout
        (root / "qa.json").unlink()
        missing_gate = run("validate", registry, "--deck", deck, "--report", validation, "--require-gates")
        assert missing_gate.returncode != 0 and "gate_report_missing" in missing_gate.stdout
        write(root / "qa.json", {"valid": True})
        deck.write_bytes(b"changed")
        broken = run("validate", registry, "--deck", deck)
        assert broken.returncode != 0 and "deck_hash_mismatch" in broken.stdout
    print("manifest registry tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
