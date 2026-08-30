#!/usr/bin/env python3
"""Regression tests for P2 multi-page, preview and strict-input gates."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="p2-guards-") as temp:
        root = Path(temp)
        references = root / "references"
        references.mkdir()
        for number in (1, 2):
            Image.new("RGB", (100, 50), (255, 255, 255)).save(references / f"slide-{number}.png")
        layout = root / "layout.json"
        write(layout, {
            "ref_width": 100,
            "ref_height": 50,
            "units": "px",
            "slides": [
                {"slide_no": 1, "texts": [{"object_id": "title-1", "x": 10, "y": 5, "w": 50, "h": 10, "source_bbox": [10, 5, 50, 10]}]},
                {"slide_no": 2, "texts": [{"object_id": "title-2", "x": 10, "y": 5, "w": 50, "h": 10, "source_bbox": [10, 5, 50, 10]}]},
            ],
        })
        report = root / "multipage.json"
        checked = run("scripts/validate_multipage_layout.py", str(references), str(layout), "--expected-pages", "2", "--expected-ratio", "2", "--strict", "--report", str(report))
        assert checked.returncode == 0, checked.stdout + checked.stderr
        assert json.loads(report.read_text(encoding="utf-8"))["valid"] is True
        (references / "slide-2.png").unlink()
        missing = run("scripts/validate_multipage_layout.py", str(references), str(layout), "--expected-pages", "2", "--expected-ratio", "2", "--strict", "--report", str(root / "missing.json"))
        assert missing.returncode == 2 and "reference_page_missing" in missing.stdout, missing.stdout

        rendered = root / "rendered"
        preview = root / "preview"
        rendered.mkdir()
        preview.mkdir()
        image = Image.new("RGB", (120, 60), (32, 64, 96))
        image.save(rendered / "slide-1.png")
        image.save(preview / "slide_01.png")
        preview_report = root / "preview.json"
        preview_ok = run("scripts/validate_preview_consistency.py", str(rendered), str(preview), "--expected-pages", "1", "--require", "--report", str(preview_report))
        assert preview_ok.returncode == 0, preview_ok.stdout + preview_ok.stderr
        assert json.loads(preview_report.read_text(encoding="utf-8"))["aggregate"]["compared_pages"] == 1
        (preview / "slide_01.png").unlink()
        preview_missing = run("scripts/validate_preview_consistency.py", str(rendered), str(preview), "--expected-pages", "1", "--require", "--report", str(root / "preview-missing.json"))
        assert preview_missing.returncode == 2 and "preview_pages_missing" in preview_missing.stdout, preview_missing.stdout

        strict_layout = root / "strict-layout.json"
        write(strict_layout, {"slide_width_in": 4, "slide_height_in": 2.25, "slides": [{"texts": [{"text": "strict", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.2, "size": 12, "align": "diagonal"}]}]})
        strict_output = run("scripts/compose_pptx.py", str(strict_layout), str(root / "strict.pptx"), "--strict-input")
        assert strict_output.returncode == 2 and "unsupported text alignment" in strict_output.stderr, strict_output.stdout + strict_output.stderr
        implicit_shape = root / "implicit-shape.json"
        write(implicit_shape, {"slide_width_in": 4, "slide_height_in": 2.25, "slides": [{"shapes": [{"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.2, "fill": "#FFFFFF"}]}]})
        implicit_output = run("scripts/compose_pptx.py", str(implicit_shape), str(root / "implicit.pptx"), "--strict-input")
        assert implicit_output.returncode == 2 and "explicit type" in implicit_output.stderr, implicit_output.stdout + implicit_output.stderr

    print("P2 multi-page, preview and strict-input gates: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
