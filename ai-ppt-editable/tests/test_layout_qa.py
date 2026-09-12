#!/usr/bin/env python3
"""Regression coverage for semantic layout findings and table geometry."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "layout_qa.py"


def invoke(manifest: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(manifest), "--strict", "--output", str(output)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        manifest = folder / "layout.json"
        manifest.write_text(json.dumps({
            "page_width": 1280, "page_height": 720,
            "objects": [{"id": "title", "position": {"left": 20, "top": 20, "width": 300, "height": 40}}],
            "tables": [{"id": "table", "position": {"left": 20, "top": 100, "width": 400, "height": 100}, "column_widths": [180, 220], "row_heights": [25, 25, 50]}],
            "overlays": [],
        }), encoding="utf-8")
        report = folder / "valid.json"
        completed = invoke(manifest, report)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert json.loads(report.read_text(encoding="utf-8"))["valid"] is True

        manifest.write_text(json.dumps({"page_width": 1280, "page_height": 720, "objects": [{"id": "bad", "position": {"left": 1270, "top": 10, "width": 30, "height": 20}}]}), encoding="utf-8")
        failed = invoke(manifest, folder / "invalid.json")
        assert failed.returncode != 0
        result = json.loads((folder / "invalid.json").read_text(encoding="utf-8"))
        assert any(item["code"] == "object_out_of_canvas" for item in result["findings"])
    print("semantic layout QA: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
