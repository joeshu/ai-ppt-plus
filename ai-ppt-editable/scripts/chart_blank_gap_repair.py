#!/usr/bin/env python3
"""Deterministically repair native-chart blank gaps after Artifact Tool export.

Artifact Tool 2.8.22 may serialize null numeric points as cached zero values even
when displayBlanksAs=gap.  This adapter uses the approved source layout as the
semantic authority and removes only the cached c:pt nodes whose source values
are null.  It also enforces c:dispBlanksAs="gap" on affected charts.

The repair is intentionally post-authoring and package-local: no geometry,
typography, assets, or non-chart objects are changed.
"""
from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"c": C, "r": R, "pr": PKG}
ET.register_namespace("c", C)
ET.register_namespace("r", R)


def _null_indexes(series: dict) -> set[int]:
    values = series.get("values")
    if values is None:
        values = series.get("data")
    if not isinstance(values, list):
        return set()
    return {idx for idx, value in enumerate(values) if value is None}


def _slide_chart_specs(deck: dict) -> list[list[dict]]:
    result = []
    for slide in deck.get("slides", []):
        charts = slide.get("charts", []) if isinstance(slide, dict) else []
        result.append([chart for chart in charts if isinstance(chart, dict)])
    return result


def _chart_targets(zf: zipfile.ZipFile, slide_index: int) -> list[str]:
    rel_name = f"ppt/slides/_rels/slide{slide_index}.xml.rels"
    try:
        root = ET.fromstring(zf.read(rel_name))
    except KeyError:
        return []
    targets = []
    for rel in root.findall("pr:Relationship", NS):
        rel_type = rel.get("Type", "")
        target = rel.get("Target", "")
        if rel_type.endswith("/chart") and target:
            if target.startswith("../"):
                target = "ppt/" + target[3:]
            elif target.startswith("/"):
                target = target[1:]
            else:
                target = f"ppt/slides/{target}"
            targets.append(str(Path(target).as_posix()))
    return targets


def _ensure_gap(root: ET.Element) -> None:
    chart = root.find("c:chart", NS)
    if chart is None:
        return
    node = chart.find("c:dispBlanksAs", NS)
    if node is None:
        node = ET.SubElement(chart, f"{{{C}}}dispBlanksAs")
    node.set("val", "gap")


def _repair_chart_xml(xml_bytes: bytes, chart_spec: dict) -> tuple[bytes, dict]:
    root = ET.fromstring(xml_bytes)
    series_specs = chart_spec.get("series", [])
    series_nodes = root.findall(".//c:ser", NS)
    removed = []
    affected = False

    for series_index, spec in enumerate(series_specs):
        if not isinstance(spec, dict):
            continue
        nulls = _null_indexes(spec)
        if not nulls:
            continue
        affected = True
        if series_index >= len(series_nodes):
            return xml_bytes, {
                "valid": False,
                "error": "series_count_mismatch",
                "series_index": series_index,
                "xml_series_count": len(series_nodes),
            }
        ser = series_nodes[series_index]
        containers = ser.findall(".//c:val/c:numRef/c:numCache", NS) + ser.findall(".//c:val/c:numLit", NS)
        for container in containers:
            for point in list(container.findall("c:pt", NS)):
                try:
                    idx = int(point.get("idx", "-1"))
                except ValueError:
                    continue
                if idx in nulls:
                    container.remove(point)
                    removed.append({"series": series_index, "idx": idx})
    if affected:
        _ensure_gap(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), {
        "valid": True,
        "affected": affected,
        "removed_points": removed,
    }


def repair_chart_blank_gaps(pptx_path: str | Path, deck: dict, report_path: str | Path | None = None) -> dict:
    pptx = Path(pptx_path).resolve()
    specs_by_slide = _slide_chart_specs(deck)
    report = {
        "schema": "ai-ppt-plus/chart-blank-gap-repair/v1",
        "pptx": str(pptx),
        "valid": True,
        "charts": [],
        "changed": False,
    }
    if not pptx.is_file():
        report.update(valid=False, error="pptx_missing")
        return report

    with zipfile.ZipFile(pptx, "r") as zin:
        replacements: dict[str, bytes] = {}
        for slide_index, chart_specs in enumerate(specs_by_slide, start=1):
            if not chart_specs:
                continue
            targets = _chart_targets(zin, slide_index)
            if len(targets) < len(chart_specs):
                report.update(valid=False, error="chart_relationship_count_mismatch", slide=slide_index)
                break
            for chart_index, chart_spec in enumerate(chart_specs):
                has_nulls = any(_null_indexes(s) for s in chart_spec.get("series", []) if isinstance(s, dict))
                if not has_nulls:
                    continue
                target = targets[chart_index]
                try:
                    original = zin.read(target)
                except KeyError:
                    report.update(valid=False, error="chart_part_missing", chart_part=target)
                    break
                repaired, detail = _repair_chart_xml(original, chart_spec)
                detail.update(slide=slide_index, chart_index=chart_index, chart_part=target)
                report["charts"].append(detail)
                if not detail.get("valid"):
                    report["valid"] = False
                    break
                if repaired != original:
                    replacements[target] = repaired
                    report["changed"] = True
            if not report["valid"]:
                break

        if report["valid"] and replacements:
            fd, temp_name = tempfile.mkstemp(prefix=f".{pptx.stem}-chart-gap-", suffix=".pptx", dir=str(pptx.parent))
            os.close(fd)
            temp_path = Path(temp_name)
            try:
                with zipfile.ZipFile(temp_path, "w") as zout:
                    for info in zin.infolist():
                        data = replacements.get(info.filename, zin.read(info.filename))
                        zout.writestr(info, data)
                os.replace(temp_path, pptx)
            finally:
                if temp_path.exists():
                    temp_path.unlink()

    if report_path:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
