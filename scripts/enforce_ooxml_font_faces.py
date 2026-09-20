#!/usr/bin/env python3
"""Bind every editable text run to one explicit DrawingML font family."""
from __future__ import annotations

import argparse
import os
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
ET.register_namespace("a", A)
ET.register_namespace("p", P)
ET.register_namespace("c", C)
ET.register_namespace("r", R)
ET.register_namespace("pic", PIC)
TEXT_PROPS = (f"{{{A}}}rPr", f"{{{A}}}defRPr", f"{{{A}}}endParaRPr")
FONT_SLOTS = (f"{{{A}}}latin", f"{{{A}}}ea", f"{{{A}}}cs")
ORDER = {"noFill": 0, "solidFill": 0, "gradFill": 0, "blipFill": 0, "pattFill": 0, "grpFill": 0, "latin": 10, "ea": 11, "cs": 12, "sym": 13, "hlinkClick": 20, "hlinkMouseOver": 21, "rtl": 22, "extLst": 99}


def enforce(input_path: Path, output_path: Path, *, family: str) -> dict:
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if not family.strip():
        raise ValueError("font family must not be empty")
    changed_parts = 0
    changed_runs = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{output_path.stem}-", suffix=".pptx", dir=output_path.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(input_path, "r") as source, zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename.startswith("ppt/") and info.filename.endswith(".xml"):
                    try:
                        root = ET.fromstring(payload)
                    except ET.ParseError:
                        root = None
                    if root is not None:
                        touched = 0
                        for node in root.iter():
                            if node.tag not in TEXT_PROPS:
                                continue
                            for tag in FONT_SLOTS:
                                child = node.find(tag)
                                if child is None:
                                    child = ET.Element(tag)
                                    node.append(child)
                                child.set("typeface", family.strip())
                            children = list(node)
                            children.sort(key=lambda child: ORDER.get(child.tag.rsplit("}", 1)[-1], 50))
                            node[:] = children
                            touched += 1
                        if touched:
                            payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                            changed_parts += 1
                            changed_runs += touched
                target.writestr(info, payload)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {"valid": True, "family": family.strip(), "changed_parts": changed_parts, "changed_text_properties": changed_runs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--family", required=True)
    args = parser.parse_args()
    try:
        print(enforce(args.input, args.output, family=args.family))
        return 0
    except Exception as exc:
        print({"valid": False, "code": "ooxml_font_face_binding_failed", "message": f"{type(exc).__name__}: {exc}"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
