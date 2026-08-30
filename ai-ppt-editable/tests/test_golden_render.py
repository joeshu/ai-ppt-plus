#!/usr/bin/env python3
"""Golden render smoke fixture for a deterministic one-slide deck."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="golden-render-") as temp:
        root = Path(temp)
        spec = root / "golden.deck.json"
        spec.write_text(json.dumps({
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [{"shapes": [{"object_id": "golden-card", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#1E3A5F"}], "texts": [{"object_id": "golden-title", "text": "Golden render", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "size": 18}]}],
        }), encoding="utf-8")
        deck = root / "golden.pptx"
        composed = subprocess.run([sys.executable, "scripts/compose_pptx.py", str(spec), str(deck)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert composed.returncode == 0, composed.stdout + composed.stderr
        render_dir = root / "rendered"
        render_report = root / "render.json"
        rendered = subprocess.run([sys.executable, "scripts/render_pptx.py", str(deck), "--output-dir", str(render_dir), "--dpi", "96", "--report", str(render_report)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert rendered.returncode == 0, rendered.stdout + rendered.stderr
        data = json.loads(render_report.read_text(encoding="utf-8"))
        assert len(data["pages"]) == 1
        with Image.open(render_dir / "slide-1.png") as image:
            assert image.width >= 320 and image.height >= 180
            assert image.width / image.height == pytest_ratio(image.width, image.height)
            assert image.getbbox() is not None
        gate = root / "gate.json"
        checked = subprocess.run([sys.executable, "scripts/validate_render.py", str(render_dir), "--expected-pages", "1", "--report", str(gate)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        assert json.loads(gate.read_text(encoding="utf-8"))["valid"] is True
    print("golden render regression: ok")
    return 0


def pytest_ratio(width: int, height: int) -> float:
    """Keep the golden fixture ratio check tolerant without pytest."""
    ratio = width / height
    assert abs(ratio - (16 / 9)) < 0.02
    return ratio


if __name__ == "__main__":
    raise SystemExit(main())
