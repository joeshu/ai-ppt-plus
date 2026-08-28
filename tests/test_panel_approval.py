#!/usr/bin/env python3
"""Small regression test for count-agnostic panel approval."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="panel-approval-") as tmp:
        root = Path(tmp)
        image = root / "source.png"
        Image.new("RGB", (1200, 1200), "white").save(image)
        for count in range(1, 10):
            candidates = []
            for i in range(count):
                y = 20 + i * 135
                candidates.append({"candidate_id": f"panel-{i + 1:02d}", "source_bbox": [20, y, 1100, 100], "confidence": 0.4})
            candidate_file = root / f"candidates-{count}.json"
            candidate_file.write_text(json.dumps({"schema": "ai-ppt-plus/panel-candidates/v1", "status": "needs-human-confirmation", "source": str(image), "source_size": [1200, 1200], "candidates": candidates}), encoding="utf-8")
            approved = root / f"approved-{count}.json"
            result = run("scripts/approve_panel_candidates.py", str(candidate_file), "--approve", "--reviewer", "regression", "--revision", f"count-{count}", "--approved-at", "2026-01-01T00:00:00Z", "--output", str(approved))
            assert result.returncode == 0, result.stderr
            data = json.loads(approved.read_text(encoding="utf-8"))
            assert data["status"] == "approved" and len(data["panels"]) == count
            check = run("scripts/validate_panel_assets.py", str(approved), "--require-approved", "--expected-count", str(count), "--strict")
            assert check.returncode == 0, check.stderr
            assets_dir = root / f"assets-{count}"
            extracted = root / f"extracted-{count}.json"
            extract = run("scripts/extract_panels.py", str(image), str(approved), "--out-dir", str(assets_dir), "--out-manifest", str(extracted))
            assert extract.returncode == 0, extract.stderr
            extracted_data = json.loads(extracted.read_text(encoding="utf-8"))
            assert all(str(panel["file"]).startswith(f"assets-{count}/") for panel in extracted_data["panels"])
            check = run("scripts/validate_panel_assets.py", str(extracted), "--assets-dir", str(root), "--require-approved", "--expected-count", str(count), "--strict")
            assert check.returncode == 0, check.stderr
    print("panel approval counts arbitrary N=1..9: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
