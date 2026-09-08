#!/usr/bin/env python3
"""Foreground weighting must prefer the candidate that matches foreground."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]


def run(candidate, reference, regions, report):
    return subprocess.run([sys.executable, "scripts/compare_visual_regions.py", str(candidate), str(reference), str(regions), "--report", str(report)], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="region-visual-") as tmp:
        root = Path(tmp)
        reference = Image.new("RGB", (200, 100), "white")
        ImageDraw.Draw(reference).rectangle((10, 10, 90, 45), fill="black")
        reference.save(root / "reference.png")
        foreground_match = reference.copy()
        ImageDraw.Draw(foreground_match).rectangle((0, 60, 199, 99), fill="gray")
        foreground_match.save(root / "foreground-match.png")
        background_match = Image.new("RGB", (200, 100), "white")
        ImageDraw.Draw(background_match).rectangle((10, 10, 90, 45), fill="red")
        background_match.save(root / "background-match.png")
        regions = {"schema": "ai-ppt-plus/regions/v1", "regions": [
            {"region_id": "title", "role": "foreground", "bbox": [0, 0, 0.5, 0.55], "weight": 3},
            {"region_id": "background", "role": "background", "bbox": [0, 0.55, 1, 0.45]},
        ]}
        (root / "regions.json").write_text(json.dumps(regions), encoding="utf-8")
        a_report, b_report = root / "a.json", root / "b.json"
        assert run(root / "foreground-match.png", root / "reference.png", root / "regions.json", a_report).returncode == 0
        assert run(root / "background-match.png", root / "reference.png", root / "regions.json", b_report).returncode == 0
        a = json.loads(a_report.read_text(encoding="utf-8"))
        b = json.loads(b_report.read_text(encoding="utf-8"))
        assert a["foreground_weighted_score"] > b["foreground_weighted_score"]
        assert a["regions"][0]["region_id"] == "background"
    print("region visual comparison: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
