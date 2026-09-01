#!/usr/bin/env python3
"""Block last-mile PPTX repackaging that loses assets, runs, or gradients."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from lxml import etree


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def slide_snapshot(root: etree._Element) -> dict:
    runs = root.xpath(".//a:r", namespaces=NS)
    run_records = []
    styled = 0
    for run in runs:
        text = "".join(run.xpath("./a:t/text()", namespaces=NS))
        run_props = run.find("{%s}rPr" % NS["a"])
        props = etree.tostring(run_props, method="c14n") if run_props is not None else b""
        if run_props is not None and (run_props.attrib or len(run_props)):
            styled += 1
        run_records.append(text.encode("utf-8") + b"\0" + props)
    return {
        "pictures": len(root.xpath(".//p:pic", namespaces=NS)),
        "text_runs": len(runs),
        "styled_text_runs": styled,
        "gradients": len(root.xpath(".//*[local-name()='gradFill']")),
        "text_style_digest": sha256(b"\n".join(run_records)),
    }


def snapshot(path: Path) -> dict:
    with ZipFile(path) as archive:
        slides = {}
        for name in sorted(n for n in archive.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")):
            slides[name] = slide_snapshot(etree.fromstring(archive.read(name)))
        media = {
            name: sha256(archive.read(name))
            for name in sorted(n for n in archive.namelist() if n.startswith("ppt/media/"))
        }
        rels = {
            name: archive.read(name).decode("utf-8", errors="replace").count('Target="/')
            for name in archive.namelist()
            if name.endswith(".rels")
        }
    return {"slides": slides, "media": media, "absolute_relationship_targets": rels}


def compare(before: dict, after: dict) -> list[dict]:
    issues: list[dict] = []
    if list(before["slides"]) != list(after["slides"]):
        issues.append({"code": "slide_parts_changed", "before": list(before["slides"]), "after": list(after["slides"])})
    for name in before["slides"]:
        if name not in after["slides"]:
            continue
        for field in ("pictures", "text_runs", "styled_text_runs", "gradients"):
            if after["slides"][name][field] != before["slides"][name][field]:
                issues.append({"code": "slide_metric_changed", "slide": name, "field": field, "before": before["slides"][name][field], "after": after["slides"][name][field]})
        if after["slides"][name]["text_style_digest"] != before["slides"][name]["text_style_digest"]:
            issues.append({"code": "text_style_digest_changed", "slide": name})
    if before["media"] != after["media"]:
        issues.append({"code": "media_bytes_changed", "before": before["media"], "after": after["media"]})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        before = snapshot(Path(args.before).resolve())
        after = snapshot(Path(args.after).resolve())
        issues = compare(before, after)
        result = {
            "schema": "ai-ppt-plus/repackaging-invariants/v1",
            "before": str(Path(args.before).resolve()),
            "after": str(Path(args.after).resolve()),
            "status": "passed" if not issues else "blocked",
            "valid": not issues,
            "issues": issues,
            "before_snapshot": before,
            "after_snapshot": after,
            "human_visual_review_required": True,
        }
    except Exception as exc:
        result = {
            "schema": "ai-ppt-plus/repackaging-invariants/v1",
            "status": "blocked",
            "valid": False,
            "issues": [{"code": "snapshot_failed", "message": f"{type(exc).__name__}: {exc}"}],
        }
    if args.report:
        Path(args.report).resolve().write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
