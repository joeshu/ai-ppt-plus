#!/usr/bin/env python3
"""Regression tests for visual comparison size normalization."""
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
    with tempfile.TemporaryDirectory(prefix="visual-compare-") as tmp:
        root = Path(tmp)
        rendered = root / "rendered.png"
        reference = root / "reference.png"
        mismatch = root / "mismatch.png"
        report = root / "report.json"
        Image.new("RGB", (40, 30), (240, 240, 240)).save(rendered)
        Image.new("RGB", (80, 60), (240, 240, 240)).save(reference)
        Image.new("RGB", (80, 80), (240, 240, 240)).save(mismatch)

        result = run("scripts/compare_visual.py", str(rendered), str(reference), "--report", str(report))
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True
        assert data["resized_for_comparison"] is True
        assert data["comparison_size"] == [80, 60]

        result = run("scripts/compare_visual.py", str(rendered), str(mismatch))
        assert result.returncode == 2, result.stdout
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["issues"][0]["code"] == "aspect_ratio_mismatch"

        qa_dir = root / "qa"
        result = run("scripts/visual_compare_qa.py", str(rendered), str(reference), "--out-dir", str(qa_dir))
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads((qa_dir / "report.json").read_text(encoding="utf-8"))
        assert data["ok"] is True and data["status"] == "diagnostic"
        assert data["resized_for_comparison"] is True

        result = run("scripts/visual_compare_qa.py", str(rendered), str(mismatch), "--out-dir", str(root / "qa-mismatch"))
        assert result.returncode == 2, result.stdout

        rendered_dir = root / "rendered-deck"
        reference_dir = root / "reference-deck"
        rendered_dir.mkdir()
        reference_dir.mkdir()
        rendered.rename(rendered_dir / "slide-1.png")
        reference.rename(reference_dir / "slide-1.png")
        result = run("scripts/compare_visual_deck.py", str(rendered_dir), str(reference_dir))
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["pages"][0]["metrics"]["resized_for_comparison"] is True
    print("visual comparison size normalization: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
