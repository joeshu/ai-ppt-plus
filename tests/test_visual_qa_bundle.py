#!/usr/bin/env python3
"""Regression coverage for same-size visual evidence and required regions."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "visual_qa_bundle.py"


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        reference = folder / "reference.png"
        render = folder / "render.png"
        Image.new("RGB", (160, 90), (40, 50, 60)).save(reference)
        Image.new("RGB", (160, 90), (42, 50, 60)).save(render)
        regions = folder / "regions.json"
        regions.write_text(json.dumps({"1": [{"name": "title", "bbox": [0, 0, 80, 30]}]}), encoding="utf-8")
        anchors = folder / "anchors.json"
        anchors.write_text(json.dumps({"1": [{"id": "title", "bbox": [0, 0, 80, 30]}]}), encoding="utf-8")
        output_dir = folder / "bundle"
        report = folder / "report.json"
        completed = subprocess.run([
            sys.executable, str(SCRIPT), "--reference", str(reference), "--render", str(render),
            "--output-dir", str(output_dir), "--regions", str(regions), "--anchors", str(anchors),
            "--strict", "--report", str(report),
        ], cwd=ROOT, text=True, capture_output=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(report.read_text(encoding="utf-8"))
        assert result["valid"] is True
        assert result["page_count"] == 1
        assert (output_dir / "slide-1-reference-vs-final.png").is_file()
        assert (output_dir / "slide-1-overlay.png").is_file()
        assert (output_dir / "slide-1-absolute-diff.png").is_file()
        assert result["pages"][0]["regions"][0]["name"] == "title"
    print("visual QA evidence bundle: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
