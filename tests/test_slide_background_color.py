#!/usr/bin/env python3
"""Regression test for native slide background colors in layout specs."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="slide-background-color-") as temp:
        root = Path(temp)
        layout = root / "layout.json"
        layout.write_text(json.dumps({
            "project_id": "background-color-fixture",
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "units": "fraction",
            "slides": [{"background_color": "#F7F0E4"}],
        }), encoding="utf-8")
        deck = root / "deck.pptx"
        completed = subprocess.run(
            [sys.executable, "scripts/compose_pptx.py", str(layout), str(deck)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        from pptx import Presentation

        slide = Presentation(str(deck)).slides[0]
        assert str(slide.background.fill.fore_color.rgb) == "F7F0E4"
    print("native slide background color: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
