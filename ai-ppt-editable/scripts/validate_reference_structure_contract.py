#!/usr/bin/env python3
"""Check source-to-slide text groups and editability before visual signoff.

This check cannot judge geometric fidelity. It catches missing source rows,
misordered labels/values, screenshot-only slides, and accidental native tables.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def validate(deck: Path, contract: dict) -> dict:
    if contract.get("schema") != "ai-ppt-plus/reference-structure-contract/v1":
        raise ValueError("invalid structure contract schema")
    issues = []
    with ZipFile(deck) as z:
        slides = sorted((n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")), key=lambda n: int(n.rsplit("slide", 1)[1][:-4]))
        if len(slides) != len(contract["slides"]):
            issues.append({"code": "slide_count", "expected": len(contract["slides"]), "actual": len(slides)})
        for index, spec in enumerate(contract["slides"]):
            if index >= len(slides):
                break
            root = ET.fromstring(z.read(slides[index]))
            objects = root.findall(f".//{P}sp")
            pictures = root.findall(f".//{P}pic")
            frames = root.findall(f".//{P}graphicFrame")
            text = "".join(node.text or "" for node in root.findall(f".//{A}t"))
            if len(objects) < spec.get("min_native_objects", 1):
                issues.append({"slide": index + 1, "code": "native_object_count", "count": len(objects)})
            if len(pictures) > spec.get("max_pictures", 100000):
                issues.append({"slide": index + 1, "code": "picture_count", "count": len(pictures)})
            if spec.get("native_tables", None) == 0 and frames:
                issues.append({"slide": index + 1, "code": "unexpected_native_table_or_graphic_frame", "count": len(frames)})
            for term in spec.get("required_terms", []):
                if term not in text:
                    issues.append({"slide": index + 1, "code": "missing_source_term", "term": term})
            for group in spec.get("ordered_groups", []):
                locations = [text.find(term) for term in group]
                if -1 in locations or locations != sorted(locations):
                    issues.append({"slide": index + 1, "code": "source_group_order", "group": group})
    return {"ok": not issues, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.pptx, json.loads(args.contract.read_text(encoding="utf-8")))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
