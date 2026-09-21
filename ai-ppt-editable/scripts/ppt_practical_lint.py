#!/usr/bin/env python3
"""Fast OOXML lint for recurring practical PowerPoint reconstruction defects."""
from __future__ import annotations

import argparse
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main", "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
EFFECT_TAGS = (b"<a:outerShdw", b"<a:glow", b"<a:softEdge", b"<a:reflection")


def lint(path: Path) -> dict:
    issues = []
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        presentation = ET.fromstring(package.read("ppt/presentation.xml"))
        size = presentation.find("p:sldSz", NS)
        slide_cx = int(size.get("cx")) if size is not None else 0
        slide_cy = int(size.get("cy")) if size is not None else 0
        for name in names:
            if not name.endswith(".xml"):
                continue
            raw = package.read(name)
            for tag in EFFECT_TAGS:
                count = raw.count(tag)
                if count:
                    issues.append({"severity": "warning", "code": "unexpected_theme_effect", "part": name, "effect": tag[3:].decode(), "count": count})
            if not re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                continue
            root = ET.fromstring(raw)
            for shape in root.findall(".//p:sp", NS):
                props = shape.find("p:spPr", NS)
                transform = props.find("a:xfrm", NS) if props is not None else None
                off = transform.find("a:off", NS) if transform is not None else None
                ext = transform.find("a:ext", NS) if transform is not None else None
                preset = props.find("a:prstGeom", NS) if props is not None else None
                if off is None or ext is None:
                    continue
                x, y, cx, cy = (int(off.get("x", 0)), int(off.get("y", 0)), int(ext.get("cx", 0)), int(ext.get("cy", 0)))
                if x == 0 and y == 0 and cx == slide_cx and cy == slide_cy and preset is not None and preset.get("prst") in {"rect", "roundRect"}:
                    issues.append({"severity": "warning", "code": "full_slide_shape_background", "part": name})
                if preset is not None and preset.get("prst") == "roundRect" and cx > cy * 4:
                    adjust = props.find(".//a:gd[@name='adj']", NS)
                    if adjust is None:
                        issues.append({"severity": "warning", "code": "rounded_rectangle_default_adjustment", "part": name})
        slide_xml = b"".join(package.read(name) for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
        if b"<a:ea" not in slide_xml and any(byte >= 0xE4 for byte in slide_xml):
            issues.append({"severity": "warning", "code": "cjk_east_asian_typeface_not_observed"})
    return {"schema": "ai-ppt-plus/ppt-practical-lint/v1", "valid": not any(item["severity"] == "error" for item in issues), "issue_count": len(issues), "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = lint(args.pptx)
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/ppt-practical-lint/v1", "valid": False, "issue_count": 1, "issues": [{"severity": "error", "code": "pptx_lint_failed", "message": str(exc)}]}
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
