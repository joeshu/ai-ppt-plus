#!/usr/bin/env python3
"""Regression tests for the canonical TextSpec/TextRunSpec model."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, "scripts/text_model.py", *map(str, args)], cwd=ROOT, capture_output=True, text=True, check=False)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="text-model-") as temp:
        root = Path(temp)
        layout = root / "layout.json"
        manifest = root / "text-layout-manifest.json"
        report = root / "validation.json"
        write(layout, {
            "project_id": "text-fixture", "units": "fraction", "ref_width": 2000, "ref_height": 1000,
            "slides": [{"slide_no": 1, "texts": [
                {"name": "title", "text": "标题", "x": .1, "y": .1, "w": .5, "h": .1, "size": 24, "font": "Noto Sans CJK SC", "color": "#FFFFFF", "source_bbox": [200, 100, 1000, 100]},
                {"name": "price", "x": .1, "y": .3, "w": .4, "h": .1, "source_bbox": [200, 300, 800, 100], "font": "Noto Sans CJK SC", "size": 20, "runs": [{"text": "优惠", "color": "#FFFFFF"}, {"text": "**元", "color": "#FF0000", "literal_redaction": True}], "literal_redaction": True, "emphasis_expected": True}
            ]}]
        })
        built = run("build", layout, "--output", manifest)
        assert built.returncode == 0, built.stderr + built.stdout
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["schema"] == "ai-ppt-plus/text-layout-manifest/v1"
        assert data["slides"][0]["text_specs"][1]["content"] == "优惠**元"
        checked = run("validate", manifest, "--require-source-bbox", "--report", report)
        assert checked.returncode == 0, checked.stdout

        bad = json.loads(manifest.read_text(encoding="utf-8"))
        bad["slides"][0]["text_specs"][1]["runs"][0]["text"] = "错"
        write(manifest, bad)
        failed = run("validate", manifest)
        assert failed.returncode == 2 and "text_runs_content_mismatch" in failed.stdout

        bad["slides"][0]["text_specs"][1]["runs"][0]["text"] = "优惠"
        bad["slides"][0]["text_specs"][1]["style"]["color"] = "red"
        write(manifest, bad)
        failed = run("validate", manifest)
        assert failed.returncode == 2 and "text_color_invalid" in failed.stdout
    print("text model contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
