#!/usr/bin/env python3
"""Regression gate for native chart missing values and final OOXML repair."""
from __future__ import annotations

import importlib.util
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
AUTHORING = ROOT / "ai-ppt-editable" / "scripts" / "artifact_tool_authoring.mjs"
REPAIR = ROOT / "ai-ppt-editable" / "scripts" / "chart_blank_gap_repair.py"
COMPOSE = ROOT / "ai-ppt-editable" / "scripts" / "compose_pptx.py"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
NS = {"c": C}


def _load_repair():
    spec = importlib.util.spec_from_file_location("chart_blank_gap_repair", REPAIR)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _fixture(path: Path) -> None:
    chart = f'''<?xml version="1.0" encoding="UTF-8"?>
<c:chartSpace xmlns:c="{C}"><c:chart><c:plotArea><c:lineChart><c:ser>
<c:val><c:numRef><c:numCache><c:ptCount val="4"/>
<c:pt idx="0"><c:v>10</c:v></c:pt><c:pt idx="1"><c:v>20</c:v></c:pt>
<c:pt idx="2"><c:v>0</c:v></c:pt><c:pt idx="3"><c:v>0</c:v></c:pt>
</c:numCache></c:numRef></c:val></c:ser></c:lineChart></c:plotArea>
<c:dispBlanksAs val="gap"/></c:chart></c:chartSpace>'''
    rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
</Relationships>'''
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
        zf.writestr("ppt/charts/chart1.xml", chart)


def main() -> int:
    source = AUTHORING.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "display_blanks_as" in source and "displayBlanksAs" in source
    assert "displayBlanksAs:" in source
    assert "repair_chart_blank_gaps" in compose
    assert "chart-blank-gap-repair.json" in compose

    forbidden = ("value ?? 0", "value || 0", "Number(value || 0)", "Number(value ?? 0)")
    chart_start = source.index("function addChart")
    chart_end = source.index("async function main", chart_start)
    assert not any(token in source[chart_start:chart_end] for token in forbidden)

    reconstruction = (ROOT / "tests" / "test_chart_reconstruction.py").read_text(encoding="utf-8")
    assert '"missing_value_policy": "blank_not_zero"' in reconstruction
    assert "missing_value_policy_invalid" in reconstruction

    module = _load_repair()
    with tempfile.TemporaryDirectory() as tmp:
        pptx = Path(tmp) / "fixture.pptx"
        _fixture(pptx)
        deck = {"slides": [{"charts": [{"series": [{"values": [10, 20, None, None]}], "displayBlanksAs": "gap"}]}]}
        result = module.repair_chart_blank_gaps(pptx, deck)
        assert result["valid"] and result["changed"]
        with zipfile.ZipFile(pptx) as zf:
            root = ET.fromstring(zf.read("ppt/charts/chart1.xml"))
        points = root.findall(".//c:pt", NS)
        assert [int(p.get("idx")) for p in points] == [0, 1]
        disp = root.find(".//c:dispBlanksAs", NS)
        assert disp is not None and disp.get("val") == "gap"

    print("native chart blank-gap contract + final OOXML repair: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
