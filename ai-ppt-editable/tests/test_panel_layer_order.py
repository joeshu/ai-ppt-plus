#!/usr/bin/env python3
"""Regression test for panel substrates staying behind native overlays."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="panel-layer-order-") as temp:
        work = Path(temp)
        panel = work / "panel.png"
        Image.new("RGBA", (120, 120), (20, 80, 180, 255)).save(panel)
        layout = work / "layout.json"
        layout.write_text(json.dumps({
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [{
                "panels": [{"object_id": "panel-substrate", "file": "panel.png", "x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5}],
                "shapes": [{"object_id": "native-overlay", "type": "rect", "x": 0.375, "y": 0.375, "w": 0.25, "h": 0.25, "fill": "#E53935", "line": "#E53935"}],
            }],
        }), encoding="utf-8")
        deck = work / "deck.pptx"
        preview_dir = work / "preview"
        result = subprocess.run(
            [sys.executable, "scripts/compose_pptx.py", str(layout), str(deck), "--preview-dir", str(preview_dir)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        with zipfile.ZipFile(deck) as package:
            slide_xml = package.read("ppt/slides/slide1.xml").decode("utf-8")
        assert slide_xml.index("panel-substrate") < slide_xml.index("native-overlay"), slide_xml

        with Image.open(preview_dir / "slide_01.png") as image:
            center = image.getpixel((800, 450))
        assert center[:3] == (229, 57, 53), center
    print("panel substrate/native overlay layer order: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
