#!/usr/bin/env python3
"""Regression tests for the split authoring modules and output policy."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from asset_placement import cleanup_temporary_files, svg_to_png  # noqa: E402
from atomic_output import atomic_replace  # noqa: E402


def main() -> int:
    compose_lines = len((ROOT / "scripts/compose_pptx.py").read_text(encoding="utf-8").splitlines())
    assert compose_lines < 250, compose_lines

    with tempfile.TemporaryDirectory(prefix="authoring-modules-") as temp:
        work = Path(temp)
        target = work / "atomic.txt"
        target.write_text("old", encoding="utf-8")

        def fail_writer(path: Path) -> None:
            path.write_text("partial", encoding="utf-8")
            raise RuntimeError("intentional writer failure")

        try:
            atomic_replace(target, fail_writer)
        except RuntimeError:
            pass
        else:
            raise AssertionError("failed writer unexpectedly succeeded")
        assert target.read_text(encoding="utf-8") == "old"
        assert not list(work.glob(f".{target.name}.*"))

        spec = work / "deck.json"
        spec.write_text(json.dumps({
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [{"texts": [{"object_id": "title", "text": "默认字体", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "size": 20}]}],
        }, ensure_ascii=False), encoding="utf-8")
        deck = work / "deck.pptx"
        composed = subprocess.run(
            [sys.executable, "scripts/compose_pptx.py", str(spec), str(deck)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert composed.returncode == 0, composed.stdout + composed.stderr
        with zipfile.ZipFile(deck) as package:
            xml = b"".join(package.read(name) for name in package.namelist() if name.endswith(".xml"))
        assert b"Noto Sans SC" in xml
        assert b"Microsoft YaHei" not in xml

        svg = work / "icon.svg"
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="#ff0000"/></svg>', encoding="utf-8")
        registered = []
        raster = svg_to_png(svg, registered)
        assert raster.is_file()
        assert registered == [raster]
        cleanup_temporary_files(registered)
        assert not raster.exists()

        svg_spec = work / "svg-deck.json"
        svg_spec.write_text(json.dumps({
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [{"icons": [{"object_id": "svg-icon", "file": "icon.svg", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}]}],
        }), encoding="utf-8")
        svg_deck = work / "svg-deck.pptx"
        composed_svg = subprocess.run(
            [sys.executable, "scripts/compose_pptx.py", str(svg_spec), str(svg_deck)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert composed_svg.returncode == 0, composed_svg.stdout + composed_svg.stderr
        with zipfile.ZipFile(svg_deck) as package:
            assert any(name.endswith(".svg") for name in package.namelist())
    print("authoring module split and atomic output: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
