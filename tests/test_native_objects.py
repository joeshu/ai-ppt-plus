#!/usr/bin/env python3
"""Regression test for native shapes, gradients, SVG assets, and groups."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_object_manifest import build  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="native-objects-") as temp:
        root = Path(temp)
        svg = root / "icon.svg"
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="8" fill="#ff0000"/></svg>', encoding="utf-8")
        deck = root / "deck.json"
        deck.write_text(json.dumps({
            "slide_width_in": 4, "slide_height_in": 2.25, "units": "fraction", "assets_dir": str(root),
            "theme": {"font": "Noto Sans CJK SC", "text_color": "#222222", "size": 10, "table_header_fill": "#FF0000", "chart_colors": ["#00AAFF"], "layout_name": "Blank"},
            "slides": [{
                "shapes": [{"object_id": "gradient-card", "type": "rounded_rect", "x": .05, "y": .1, "w": .4, "h": .7,
                            "gradient": {"angle": 90, "stops": [{"position": 0, "color": "#FF0000"}, {"position": 1, "color": "#0000FF", "opacity": .8}]},
                            "alt_text": "渐变卡片"}],
                "groups": [{"object_id": "component-1", "x": .5, "y": .1, "w": .4, "h": .7, "children_coordinate_space": "local",
                            "alt_text": "组合组件", "children": [
                                {"object_id": "component-bg", "type": "rect", "x": 0, "y": 0, "w": 1, "h": .5, "fill": "#FFFFFF"},
                                {"object_id": "component-dot", "type": "oval", "x": .1, "y": .5, "w": .3, "h": .4, "fill": "#00FF00"}]}],
                "icons": [{"object_id": "vector-icon", "file": "icon.svg", "x": .85, "y": .05, "w": .1, "h": .1, "alt_text": "矢量图标"}],
                "tables": [{"object_id": "data-table", "x": .05, "y": .02, "w": .35, "h": .06, "rows": [["A", "B"], ["1", "2"]], "data_source": "fixture", "merges": [[0, 0, 0, 1]]}],
                "charts": [{"object_id": "data-chart", "type": "column", "x": .55, "y": .82, "w": .35, "h": .15, "categories": ["A", "B"], "series": [{"name": "数量", "values": [1, 2]}], "data_source": "fixture", "data_labels": True}],
                "speaker_notes": "这是演讲者备注。",
                "texts": [{"object_id": "label", "text": "可编辑", "x": .05, "y": .85, "w": .3, "h": .1, "size": 12}]
            }]
        }, ensure_ascii=False), encoding="utf-8")
        output = root / "deck.pptx"
        composed = subprocess.run([sys.executable, "scripts/compose_pptx.py", str(deck), str(output)], cwd=ROOT, capture_output=True, text=True)
        assert composed.returncode == 0, composed.stderr + composed.stdout
        with zipfile.ZipFile(output) as package:
            slide_xml = package.read("ppt/slides/slide1.xml")
            names = set(package.namelist())
            assert b"<a:gradFill" in slide_xml
            assert b"<p:grpSp" in slide_xml
            assert b"gradient-card" in slide_xml and b"component-1" in slide_xml and b"component-dot" in slide_xml
            assert b' descr="%E6' not in slide_xml  # XML stores UTF-8 text, not URL encoding.
            assert any(name.casefold().endswith(".svg") for name in names)
            assert b"data-table" in slide_xml and b"data-chart" in slide_xml
            assert "演讲者备注".encode() in b"".join(package.read(name) for name in names if "notesSlides/notesSlide" in name)
        report = root / "inspect.json"
        inspected = subprocess.run([sys.executable, "scripts/inspect_pptx.py", str(output), "--report", str(report)], cwd=ROOT, capture_output=True, text=True)
        assert inspected.returncode == 0, inspected.stdout + inspected.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["slides"][0]["groups"] == 1
        assert data["slides"][0]["gradient_fills"] >= 1
        assert data["slides"][0]["tables"] >= 1 and data["slides"][0]["charts"] >= 1, data["slides"][0]
        assert len(data["vector_assets"]) == 1
        manifest = build(json.loads(deck.read_text(encoding="utf-8")), None, None)
        objects = {item["object_id"]: item for item in manifest["slides"][0]["objects"]}
        assert objects["component-1"]["children"] == ["component-bg", "component-dot"]
        assert objects["vector-icon"]["vector_asset"] is True
        assert objects["vector-icon"]["editability_level"] == "L2"
        assert objects["data-table"]["object_type"] == "editable_table"
        assert objects["data-chart"]["object_type"] == "editable_chart"
    print("native objects contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
