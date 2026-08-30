#!/usr/bin/env python3
"""Regression tests for phone/viewer letterbox normalization."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="viewer-capture-") as temp:
        root = Path(temp)
        content = Image.new("RGB", (1262, 710), (238, 230, 214))
        draw = ImageDraw.Draw(content)
        draw.rectangle((40, 40, 420, 110), fill=(185, 125, 36))
        draw.rectangle((720, 180, 1180, 620), outline=(40, 40, 40), width=3)
        rendered = root / "rendered.png"
        content.save(rendered)

        capture = Image.new("RGB", (1536, 710), (0, 0, 0))
        capture.paste(content, (137, 0))
        reference = root / "phone-wps.png"
        capture.save(reference)

        no_bar = root / "no-bar.png"
        no_bar_content = content.copy()
        ImageDraw.Draw(no_bar_content).rectangle((0, 0, 5, 5), fill=(0, 0, 0))
        no_bar_content.save(no_bar)

        sys.path.insert(0, str(ROOT / "scripts"))
        from image_viewport import detect_viewer_crop

        with Image.open(reference) as image:
            crop = detect_viewer_crop(image.convert("RGB"), expected_ratio=16 / 9)
        assert crop["detected"] is True
        assert crop["crop_box"] == [137, 0, 1399, 710]
        assert crop["artifact_classification"] == "viewer_only_capture_chrome"
        assert crop["content_size"] == [1262, 710]
        with Image.open(no_bar) as image:
            no_crop = detect_viewer_crop(image.convert("RGB"), expected_ratio=16 / 9)
            assert no_crop["detected"] is False
            assert no_crop["artifact_classification"] == "none"

        comparison = root / "comparison.json"
        checked = run("scripts/compare_visual.py", str(rendered), str(reference), "--report", str(comparison))
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(comparison.read_text(encoding="utf-8"))
        assert data["valid"] is True
        assert data["viewer_crops"]["reference"]["detected"] is True
        assert data["normalized_sizes"]["reference"] == [1262, 710]
        assert data["metrics"]["mean_absolute_error"] < 0.001

        audit = root / "audit.json"
        checked = run("scripts/reference_audit.py", str(reference), str(rendered), "--report", str(audit))
        assert checked.returncode == 0, checked.stdout + checked.stderr
        audit_data = json.loads(audit.read_text(encoding="utf-8"))
        assert audit_data["valid"] is True
        assert audit_data["reference_stats"]["viewer_crop"]["detected"] is True

    print("viewer capture normalization: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
