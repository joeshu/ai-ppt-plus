#!/usr/bin/env python3
"""Repair only known DrawingML rich-text child ordering inside a PPTX ZIP."""
from __future__ import annotations

import argparse
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from atomic_output import atomic_write_bytes, atomic_write_json


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
TARGETS = {f"{{{A_NS}}}{name}" for name in ("rPr", "defRPr", "endParaRPr")}
ORDER = {
    "noFill": 0, "solidFill": 0, "gradFill": 0, "blipFill": 0, "pattFill": 0, "grpFill": 0,
    "latin": 10, "ea": 11, "cs": 12, "sym": 13, "hlinkClick": 20,
    "hlinkMouseOver": 21, "rtl": 22, "extLst": 99,
}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_xml(payload: bytes, strict: bool) -> tuple[bytes, list[dict], list[dict]]:
    root = ET.fromstring(payload)
    changes: list[dict] = []
    issues: list[dict] = []
    for parent in root.iter():
        if parent.tag not in TARGETS:
            continue
        children = list(parent)
        unknown = [local(child.tag) for child in children if local(child.tag) not in ORDER]
        if unknown:
            issue = {"severity": "blocker", "code": "unknown_rich_text_child", "parent": local(parent.tag), "children": unknown}
            issues.append(issue)
            if strict:
                continue
        original = [local(child.tag) for child in children]
        indexed = list(enumerate(children))
        indexed.sort(key=lambda item: (ORDER.get(local(item[1].tag), 50), item[0]))
        ordered = [child for _, child in indexed]
        observed = [local(child.tag) for child in ordered]
        if original != observed:
            parent[:] = ordered
            changes.append({"parent": local(parent.tag), "before": original, "after": observed})
    ET.register_namespace("a", A_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), changes, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    source = Path(args.input).resolve()
    destination = Path(args.output).resolve()
    entries: dict[str, bytes] = {}
    changes: list[dict] = []
    issues: list[dict] = []
    try:
        with zipfile.ZipFile(source, "r") as archive:
            for info in archive.infolist():
                payload = archive.read(info.filename)
                if info.filename.startswith("ppt/slides/") and info.filename.endswith(".xml"):
                    try:
                        payload, local_changes, local_issues = normalize_xml(payload, args.strict)
                        changes.extend([{**item, "part": info.filename} for item in local_changes])
                        issues.extend([{**item, "part": info.filename} for item in local_issues])
                    except ET.ParseError as exc:
                        issues.append({"severity": "blocker", "code": "slide_xml_parse_failed", "part": info.filename, "message": str(exc)})
                entries[info.filename] = payload
    except (OSError, zipfile.BadZipFile) as exc:
        issues.append({"severity": "blocker", "code": "pptx_zip_unreadable", "message": f"{type(exc).__name__}: {exc}"})
    if not issues or not args.strict:
        if entries:
            def write(path: Path) -> None:
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                    for name, payload in entries.items(): archive.writestr(name, payload)
            from atomic_output import atomic_replace
            atomic_replace(destination, write, suffix=".tmp.pptx")
    result = {"schema": "ai-ppt-plus/ooxml-rich-text-normalization/v1", "valid": not issues,
              "status": "passed" if not issues else "blocked", "strict": args.strict,
              "input": str(source), "output": str(destination), "changed_count": len(changes),
              "changes": changes, "issues": issues,
              "rule": "Only known child order in a:rPr, a:defRPr and a:endParaRPr may change; unknown children block strict mode."}
    if args.report: atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
