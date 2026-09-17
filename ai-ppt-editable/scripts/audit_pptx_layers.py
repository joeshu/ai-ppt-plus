#!/usr/bin/env python3
"""Audit physical PPTX shape-tree order for icon and text visibility."""
from __future__ import annotations

import argparse
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _name(node: ET.Element) -> str:
    prop = node.find(f".//{{{P}}}cNvPr")
    return prop.get("name", "") if prop is not None else ""


def _has_text(node: ET.Element) -> bool:
    return any((item.text or "").strip() for item in node.findall(f".//{{{A}}}t"))


def audit(path: Path, icon_pattern: str = r"(?i)(^|[-_ ])(icon|imagegen|pictogram|badge)([-_ ]|$)") -> dict:
    matcher = re.compile(icon_pattern)
    slides: list[dict] = []
    issues: list[dict] = []
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=lambda value: int(re.search(r"\d+", value).group()),
        )
        for slide_number, member in enumerate(names, 1):
            root = ET.fromstring(archive.read(member))
            tree = root.find(f".//{{{P}}}spTree")
            rows = []
            for index, node in enumerate(list(tree) if tree is not None else []):
                local = node.tag.rsplit("}", 1)[-1]
                if local not in {"sp", "pic", "grpSp", "graphicFrame", "cxnSp"}:
                    continue
                name = _name(node)
                role = "icon" if local == "pic" and matcher.search(name) else "text" if _has_text(node) else "native"
                rows.append({"index": index, "type": local, "name": name, "role": role})
            icon_indices = [row["index"] for row in rows if row["role"] == "icon"]
            for row in rows:
                if row["role"] == "text" and any(row["index"] < icon_index for icon_index in icon_indices):
                    issues.append({"code": "text_below_icon", "slide": slide_number, "object": row["name"]})
                if row["role"] == "native" and any(row["index"] > icon_index for icon_index in icon_indices):
                    issues.append({"code": "native_object_above_icon", "slide": slide_number, "object": row["name"]})
            slides.append({"slide": slide_number, "shape_tree": rows})
    return {
        "schema": "ai-ppt-plus/pptx-layer-audit/v1",
        "valid": not issues,
        "pptx": str(path),
        "icon_pattern": icon_pattern,
        "slides": slides,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--icon-pattern", default=r"(?i)(^|[-_ ])(icon|imagegen|pictogram|badge)([-_ ]|$)")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = audit(args.pptx.resolve(), args.icon_pattern)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
