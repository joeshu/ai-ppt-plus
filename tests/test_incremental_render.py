#!/usr/bin/env python3
"""Selected-page rendering preserves slide numbers and excludes unaffected pages."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="incremental-render-") as temp:
        root = Path(temp)
        spec = root / "deck.json"
        spec.write_text(json.dumps({
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [
                {"shapes": [{"object_id": "s1", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#1E3A5F"}], "texts": [{"object_id": "t1", "text": "Page one", "x": 0.1, "y": 0.1, "w": 1.2, "h": 0.3, "size": 18}]},
                {"shapes": [{"object_id": "s2", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#7F1D1D"}], "texts": [{"object_id": "t2", "text": "Page two", "x": 0.1, "y": 0.1, "w": 1.2, "h": 0.3, "size": 18}]},
            ],
        }), encoding="utf-8")
        deck = root / "deck.pptx"
        composed = subprocess.run([sys.executable, "scripts/compose_pptx.py", str(spec), str(deck)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert composed.returncode == 0, composed.stdout + composed.stderr
        render_dir = root / "rendered"
        report = root / "render.json"
        rendered = subprocess.run([sys.executable, "scripts/render_pptx.py", str(deck), "--output-dir", str(render_dir), "--pages", "2", "--report", str(report)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert rendered.returncode == 0, rendered.stdout + rendered.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["selected_pages"] == [2] and [Path(page).name for page in data["pages"]] == ["slide-2.png"]
        assert (render_dir / "slide-2.png").is_file() and not (render_dir / "slide-1.png").exists()
        gate = root / "gate.json"
        checked = subprocess.run([sys.executable, "scripts/validate_render.py", str(render_dir), "--expected-pages", "1", "--pages", "2", "--report", str(gate)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        gate_data = json.loads(gate.read_text(encoding="utf-8"))
        assert gate_data["selected_pages"] == [2] and gate_data["pages"][0]["page"] == "slide-2.png"
    print("incremental selected-page render: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
