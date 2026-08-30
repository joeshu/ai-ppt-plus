#!/usr/bin/env python3
"""Polygonal regions remain valid without a fixed rectangle/grid assumption."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="irregular-regions-") as temp:
        root = Path(temp)
        manifest = root / "regions.json"
        manifest.write_text(json.dumps({
            "schema": "ai-ppt-plus/regions/v1",
            "canvas": [1000, 800],
            "regions": [
                {"region_id": "concave-a", "polygon": [[50, 50], [450, 50], [450, 250], [260, 250], [260, 650], [50, 650]], "object_id": "panel-a"},
                {"region_id": "triangle-b", "polygon": [[550, 100], [900, 100], [720, 500]], "object_id": "panel-b"},
                {"region_id": "box-c", "bbox": [100, 680, 700, 80], "object_id": "panel-c"},
            ]
        }), encoding="utf-8")
        report = root / "report.json"
        checked = subprocess.run([sys.executable, "scripts/validate_regions.py", str(manifest), "--report", str(report)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True and data["region_count"] == 3
        bad = root / "bad.json"
        bad.write_text(manifest.read_text(encoding="utf-8").replace("[550, 100]", "[1200, 100]"), encoding="utf-8")
        failed = subprocess.run([sys.executable, "scripts/validate_regions.py", str(bad), "--report", str(root / "bad-report.json")], cwd=ROOT, capture_output=True, text=True, check=False)
        assert failed.returncode == 2
        assert any(item["code"] == "polygon_out_of_bounds" for item in json.loads((root / "bad-report.json").read_text(encoding="utf-8"))["issues"])
    print("irregular region contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
