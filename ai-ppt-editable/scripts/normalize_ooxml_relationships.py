#!/usr/bin/env python3
"""Normalize package-relative OOXML relationship targets without reauthoring PPTX.

This is a last-mile compatibility adapter. It rewrites only root-relative
relationship targets to the equivalent package-relative URI. It deliberately
does not open/save the deck through python-pptx, because a second authoring
pass can change rich-text runs, gradient fills, extension elements, or media
relationships.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import posixpath
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_TAG = f"{{{REL_NS}}}Relationship"
ET.register_namespace("", REL_NS)


def source_part_for_relationships(name: str) -> str:
    if name == "_rels/.rels":
        return ""
    parent, filename = posixpath.split(name)
    if not parent.endswith("/_rels") or not filename.endswith(".rels"):
        raise ValueError(f"not a relationship part: {name}")
    source_dir = parent[: -len("/_rels")]
    source_name = filename[: -len(".rels")]
    return posixpath.join(source_dir, source_name) if source_dir else source_name


def normalize_target(rels_name: str, target: str) -> str:
    if not target.startswith("/"):
        return target
    root_target = target.lstrip("/")
    source_part = source_part_for_relationships(rels_name)
    source_dir = posixpath.dirname(source_part)
    return posixpath.relpath(root_target, source_dir or ".")


def rewrite_relationships(name: str, payload: bytes) -> tuple[bytes, list[dict]]:
    root = ET.fromstring(payload)
    changes: list[dict] = []
    for relationship in root.findall(REL_TAG):
        target = relationship.get("Target")
        if not target:
            continue
        normalized = normalize_target(name, target)
        if normalized != target:
            relationship.set("Target", normalized)
            changes.append({"id": relationship.get("Id"), "before": target, "after": normalized})
    if not changes:
        return payload, changes
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), changes


def normalize_package(source: Path, output: Path) -> dict:
    if source.resolve() == output.resolve():
        raise ValueError("output must be different from input")
    output.parent.mkdir(parents=True, exist_ok=True)
    changed_parts: list[dict] = []
    with zipfile.ZipFile(source, "r") as zin:
        with tempfile.NamedTemporaryFile(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            with zipfile.ZipFile(temp_path, "w") as zout:
                for info in zin.infolist():
                    payload = zin.read(info.filename)
                    if info.filename.endswith(".rels"):
                        payload, changes = rewrite_relationships(info.filename, payload)
                        if changes:
                            changed_parts.append({"part": info.filename, "changes": changes})
                    zout.writestr(copy.copy(info), payload)
            os.replace(temp_path, output)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
    return {
        "schema": "ai-ppt-plus/ooxml-relationship-normalization/v1",
        "input": str(source),
        "output": str(output),
        "changed_part_count": len(changed_parts),
        "changed_parts": changed_parts,
        "semantic_authoring_pass": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        result = normalize_package(Path(args.input).resolve(), Path(args.output).resolve())
        result["status"] = "passed"
        result["valid"] = True
        if args.report:
            Path(args.report).resolve().write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        result = {
            "schema": "ai-ppt-plus/ooxml-relationship-normalization/v1",
            "status": "blocked",
            "valid": False,
            "error": f"{type(exc).__name__}: {exc}",
            "semantic_authoring_pass": False,
        }
        if args.report:
            Path(args.report).resolve().write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
