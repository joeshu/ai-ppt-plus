#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chart_blank_series_materializes_gap_workbook():
    module = _load("patch_chart_blank_series")
    chart = '''<?xml version="1.0" encoding="UTF-8"?><c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><c:chart><c:plotArea><c:lineChart><c:ser><c:idx val="0"/><c:order val="0"/><c:tx><c:v>2025</c:v></c:tx><c:cat><c:strLit><c:ptCount val="4"/><c:pt idx="0"><c:v>1月</c:v></c:pt><c:pt idx="1"><c:v>2月</c:v></c:pt><c:pt idx="2"><c:v>3月</c:v></c:pt><c:pt idx="3"><c:v>4月</c:v></c:pt></c:strLit></c:cat><c:val><c:numLit><c:ptCount val="4"/><c:pt idx="0"><c:v>10</c:v></c:pt><c:pt idx="1"><c:v>20</c:v></c:pt><c:pt idx="2"><c:v>30</c:v></c:pt><c:pt idx="3"><c:v>40</c:v></c:pt></c:numLit></c:val></c:ser><c:ser><c:idx val="1"/><c:order val="1"/><c:tx><c:v>2026</c:v></c:tx><c:cat><c:strLit><c:ptCount val="4"/><c:pt idx="0"><c:v>1月</c:v></c:pt><c:pt idx="1"><c:v>2月</c:v></c:pt><c:pt idx="2"><c:v>3月</c:v></c:pt><c:pt idx="3"><c:v>4月</c:v></c:pt></c:strLit></c:cat><c:val><c:numLit><c:ptCount val="4"/><c:pt idx="0"><c:v>9</c:v></c:pt><c:pt idx="1"><c:v>19</c:v></c:pt><c:pt idx="2"><c:v>29</c:v></c:pt><c:pt idx="3"><c:v>0</c:v></c:pt></c:numLit></c:val></c:ser></c:lineChart></c:plotArea></c:chart></c:chartSpace>'''
    content_types = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>'
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        source, output = temp / "in.pptx", temp / "out.pptx"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("ppt/slides/charts/chart1.xml", chart)
        report = module.patch_chart(source, output, chart_index=0, series_index=1, first_blank_index=3)
        assert report["patched_series_count"] == 3
        with zipfile.ZipFile(output) as archive:
            xml = archive.read("ppt/slides/charts/chart1.xml").decode("utf-8")
            assert "'ChartData'!$C$2:$C$4" in xml and "dispBlanksAs" in xml
            wb = load_workbook(io.BytesIO(archive.read(report["workbook_path"])), data_only=True)
            assert wb["ChartData"]["C5"].value is None


def test_alpha_centroid_layout_centers_visible_subject():
    module = _load("normalize_layout_fidelity")
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((5, 30, 45, 70), fill=(255, 0, 0, 255))
        image.save(temp / "icon.png")
        layout = {"units": "px", "ref_width": 1000, "ref_height": 500, "assets_dir": str(temp), "slides": [{"icons": [{"object_id": "i", "file": "icon.png", "x": 100, "y": 100, "w": 100, "h": 100, "placement_mode": "alpha-centroid-fit", "visual_scale": 0.8}]}]}
        source = temp / "layout.json"
        source.write_text(json.dumps(layout), encoding="utf-8")
        deck, records = module.normalize(source)
        assert len(records) == 1
        assert deck["slides"][0]["icons"][0]["placement_mode"] == "contain"
        rec = records[0]
        x, y, w, h = rec["placed_canvas_px"]
        geo = rec["alpha_geometry"]
        assert abs((x + geo["centroid_x"] * w / geo["canvas_w"]) - 150) < 0.01
        assert abs((y + geo["centroid_y"] * h / geo["canvas_h"]) - 150) < 0.01


def test_text_fit_deck_covers_all_text_paths():
    module = _load("text_fit_deck")
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        layout = {"units": "px", "ref_width": 1000, "ref_height": 500, "slides": [{"texts": [{"object_id": "t", "text": "标题", "x": 0, "y": 0, "w": 300, "h": 80, "font_size_pt": 24}], "shapes": [{"object_id": "s", "text": "卡片", "x": 0, "y": 90, "w": 300, "h": 80, "font_size_pt": 16}], "tables": [{"object_id": "tbl", "x": 0, "y": 180, "w": 400, "h": 120, "columns": 2, "rows": [["A", "B"], ["C", "D"]], "font_size_pt": 12}], "charts": [{"object_id": "ch", "x": 0, "y": 310, "w": 500, "h": 180, "title": "趋势"}]}]}
        source = temp / "layout.json"
        source.write_text(json.dumps(layout), encoding="utf-8")
        font = ROOT / "assets" / "fonts" / "NotoSansSC-Regular.ttf"
        report = module.audit_layout(source, font_file=str(font))
        assert report["slot_count"] == 7 and report["all_slots_measured"] is True


def test_contact_sheet_is_quarantined():
    module = _load("curate_icon_assets")
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        assets, qa = temp / "icons", temp / "qa"
        assets.mkdir()
        (assets / "icon_r1c1.png").write_bytes(b"icon")
        (assets / "icons_contact_sheet.png").write_bytes(b"sheet")
        report = module.curate(assets, qa)
        assert report["valid"] and report["moved_count"] == 1
        assert (assets / "icon_r1c1.png").exists() and not (assets / "icons_contact_sheet.png").exists()


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("last-mile v2 tests: ok")
