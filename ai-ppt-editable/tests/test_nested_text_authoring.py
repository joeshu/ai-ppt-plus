"""Regression test for the canonical nested text manifest authoring path."""
from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_nested_style_and_run_style_survive_composition(tmp_path: Path):
    assets = tmp_path / "assets"
    assets.mkdir()
    layout = tmp_path / "layout.json"
    output = tmp_path / "nested.pptx"
    layout.write_text(json.dumps({
        "slide_width_in": 13.333,
        "slide_height_in": 7.5,
        "units": "fraction",
        "ref_width": 1536,
        "ref_height": 864,
        "assets_dir": str(assets),
        "theme": {"font": "Noto Sans CJK SC", "text_color": "#222222"},
        "slides": [{
            "layout_index": 6,
            "texts": [{
                "object_id": "title",
                "bbox": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.1},
                "content": "普通高亮",
                "style": {"font_family": "Noto Sans CJK SC", "size_px": 24, "color": "#FFFFFF", "bold": True},
                "runs": [
                    {"text": "普通", "style": {"color": "#FFFFFF", "bold": True}},
                    {"text": "高亮", "style": {"color": "#FFD33D", "bold": True}},
                ],
            }]
        }]
    }, ensure_ascii=False), encoding="utf-8")
    subprocess.run([sys.executable, "scripts/compose_pptx.py", str(layout), str(output)], cwd=ROOT, check=True)
    with zipfile.ZipFile(output) as package:
        xml = package.read("ppt/slides/slide1.xml")
    assert b"FFD33D" in xml
    assert b"FFFFFF" in xml
    assert b"Noto Sans CJK SC" in xml
