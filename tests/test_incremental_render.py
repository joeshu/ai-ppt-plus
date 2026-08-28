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

        page_cache = root / "page-cache"
        first_dir = root / "full-render"
        first_report = root / "full-render.json"
        first = subprocess.run(
            [sys.executable, "scripts/render_pptx.py", str(deck), "--output-dir", str(first_dir), "--page-cache-dir", str(page_cache), "--report", str(first_report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert first.returncode == 0, first.stdout + first.stderr
        first_data = json.loads(first_report.read_text(encoding="utf-8"))
        assert first_data["page_cache"]["hits"] == 0 and first_data["page_cache"]["misses"] == 2
        assert first_data["conversion"]["attempted"] is True and first_data["conversion"]["skipped"] is False

        cached_dir = root / "cached-render"
        cached_report = root / "cached-render.json"
        cached = subprocess.run(
            [sys.executable, "scripts/render_pptx.py", str(deck), "--output-dir", str(cached_dir), "--page-cache-dir", str(page_cache), "--report", str(cached_report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert cached.returncode == 0, cached.stdout + cached.stderr
        cached_data = json.loads(cached_report.read_text(encoding="utf-8"))
        assert cached_data["page_cache"]["hits"] == 2 and cached_data["page_cache"]["misses"] == 0
        assert cached_data["conversion"]["attempted"] is False and cached_data["conversion"]["skipped"] is True
        assert cached_data["renderer"] == "page-cache"
        assert cached_data["render_attempts"] == []

        corrupted_entry = next(page_cache.rglob("slide-1-*.png"))
        corrupted_entry.write_bytes(b"not-a-png")
        repaired_dir = root / "repaired-render"
        repaired_report = root / "repaired-render.json"
        repaired = subprocess.run(
            [sys.executable, "scripts/render_pptx.py", str(deck), "--output-dir", str(repaired_dir), "--page-cache-dir", str(page_cache), "--report", str(repaired_report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert repaired.returncode == 0, repaired.stdout + repaired.stderr
        repaired_data = json.loads(repaired_report.read_text(encoding="utf-8"))
        assert repaired_data["page_cache"]["hits"] == 1 and repaired_data["page_cache"]["misses"] == 1
        assert repaired_data["page_cache"]["stored"] == 1

        changed_spec = root / "changed-deck.json"
        changed_spec.write_text(json.dumps({
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [
                {"shapes": [{"object_id": "s1", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#1E3A5F"}], "texts": [{"object_id": "t1", "text": "Page one", "x": 0.1, "y": 0.1, "w": 1.2, "h": 0.3, "size": 18}]},
                {"shapes": [{"object_id": "s2", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#7F1D1D"}], "texts": [{"object_id": "t2", "text": "Page two changed", "x": 0.1, "y": 0.1, "w": 1.2, "h": 0.3, "size": 18}]},
            ],
        }), encoding="utf-8")
        changed_deck = root / "changed.pptx"
        changed_composed = subprocess.run([sys.executable, "scripts/compose_pptx.py", str(changed_spec), str(changed_deck)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert changed_composed.returncode == 0, changed_composed.stdout + changed_composed.stderr
        changed_dir = root / "changed-render"
        changed_report = root / "changed-render.json"
        changed = subprocess.run(
            [sys.executable, "scripts/render_pptx.py", str(changed_deck), "--output-dir", str(changed_dir), "--page-cache-dir", str(page_cache), "--report", str(changed_report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert changed.returncode == 0, changed.stdout + changed.stderr
        changed_data = json.loads(changed_report.read_text(encoding="utf-8"))
        assert changed_data["page_cache"]["hits"] == 1 and changed_data["page_cache"]["misses"] == 1
        assert changed_data["conversion"]["attempted"] is True and changed_data["conversion"]["skipped"] is False
        first_fingerprints = {item["page"]: item["fingerprint"] for item in first_data["page_fingerprints"]}
        changed_fingerprints = {item["page"]: item["fingerprint"] for item in changed_data["page_fingerprints"]}
        assert changed_fingerprints[1] == first_fingerprints[1]
        assert changed_fingerprints[2] != first_fingerprints[2]
        assert [Path(page).name for page in changed_data["pages"]] == ["slide-1.png", "slide-2.png"]
        assert (changed_dir / "slide-1.png").read_bytes() == (first_dir / "slide-1.png").read_bytes()
        assert (changed_dir / "slide-2.png").read_bytes() != (first_dir / "slide-2.png").read_bytes()
    print("incremental selected-page render: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())