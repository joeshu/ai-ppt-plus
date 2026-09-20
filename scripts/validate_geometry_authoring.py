#!/usr/bin/env python3
"""Validate resolved geometry against the authored PowerPoint XML."""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A, "p": P}
SCHEMA = "ai-ppt-plus/geometry-authoring-audit/v1"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _expected_points(parameters: dict) -> list[tuple[int, int]]:
    direction = str(parameters.get("direction") or "down").lower()
    taper = float(parameters.get("taper_ratio", 0.35))
    narrow = max(0.02, 1.0 - taper)
    if direction == "down":
        points = [(0, 0), (1, 0), (0.5 + narrow / 2, 1), (0.5 - narrow / 2, 1)]
    elif direction == "up":
        points = [(0.5 - narrow / 2, 0), (0.5 + narrow / 2, 0), (1, 1), (0, 1)]
    elif direction == "right":
        points = [(0, 0), (1, 0.5 - narrow / 2), (1, 0.5 + narrow / 2), (0, 1)]
    elif direction == "left":
        points = [(0, 0.5 - narrow / 2), (1, 0), (1, 1), (0, 0.5 + narrow / 2)]
    else:
        raise ValueError(f"unsupported direction: {direction}")
    return [(round(x * 100000), round(y * 100000)) for x, y in points]


def _path_points(path: ET.Element) -> list[tuple[int, int]]:
    result = []
    for node in path.findall("a:moveTo/a:pt", NS) + path.findall("a:lnTo/a:pt", NS):
        result.append((int(node.get("x", "-1")), int(node.get("y", "-1"))))
    return result


def _control_points(parameters: dict) -> list[tuple[float, float]] | None:
    raw = parameters.get("control_points") if isinstance(parameters, dict) else None
    if isinstance(raw, dict):
        raw = [raw.get("start"), raw.get("control1"), raw.get("control2"), raw.get("end")]
    if not isinstance(raw, list):
        return None
    points = []
    for value in raw:
        if isinstance(value, dict):
            x, y = value.get("x"), value.get("y")
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            x, y = value[0], value[1]
        else:
            return None
        try:
            x, y = float(x), float(y)
        except (TypeError, ValueError):
            return None
        if not (0 <= x <= 1 and 0 <= y <= 1):
            return None
        points.append((x, y))
    return points


def _emu_points(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    return [(round(x * 100000), round(y * 100000)) for x, y in points]


def _ooxml_path_control_points(path: ET.Element) -> tuple[list[tuple[int, int]], list[dict]]:
    points: list[tuple[int, int]] = []
    malformed: list[dict] = []
    for index, cubic in enumerate(path.findall("a:cubicBezTo", NS)):
        raw = cubic.findall("a:pt", NS)
        if len(raw) != 3:
            malformed.append({"segment": index, "point_count": len(raw)})
            continue
        for point in raw:
            try:
                points.append((int(point.get("x", "-1")), int(point.get("y", "-1"))))
            except (TypeError, ValueError):
                malformed.append({"segment": index, "point": point.attrib})
    return points, malformed


def _object_name_matches(name: str | None, object_id: str) -> bool:
    """Match top-level ids and Artifact Tool's group/child stable names."""
    return bool(name) and (name == object_id or name.endswith(f"/{object_id}"))


def audit(resolution: dict, pptx: Path) -> dict:
    issues: list[dict] = []
    resolutions = [item for item in resolution.get("resolutions", []) if isinstance(item, dict)]
    expected_cubic = 0
    for item in resolutions:
        if item.get("primitive") == "FREEFORM_BEZIER":
            controls = _control_points(item.get("parameters") or {})
            expected_cubic += max(1, (len(controls) - 1) // 3) if controls else 1
    with zipfile.ZipFile(pptx, "r") as archive:
        slide_payloads = {
            int(name[len("ppt/slides/slide"):-len(".xml")]): archive.read(name)
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml") and name[len("ppt/slides/slide"):-len(".xml")].isdigit()
        }
    roots = {page: ET.fromstring(payload) for page, payload in slide_payloads.items()}
    has_shape_tree = any(root.findall(".//p:sp", NS) for root in roots.values())
    actual_cubic = sum(len(root.findall(".//a:cubicBezTo", NS)) for root in roots.values())
    if not has_shape_tree:
        actual_cubic = sum(len(re.findall(rb"<a:cubicBezTo(?:\s|>)", payload)) for payload in slide_payloads.values())

    if not has_shape_tree:
        # Preserve the original synthetic fixture contract; real PPTX files
        # always have p:sp shape trees.
        if expected_cubic and actual_cubic < expected_cubic:
            issues.append({"severity": "blocker", "code": "geometry_cubic_bezier_missing_in_ooxml", "detail": f"expected at least {expected_cubic} cubic Bezier path(s), found {actual_cubic}"})
    else:
        for item in resolutions:
            primitive = str(item.get("primitive") or "").upper()
            if primitive not in {"ROUNDRECT", "TRAPEZOID", "FUNNEL", "FREEFORM_BEZIER"}:
                continue
            page = int(item.get("page") or 1)
            oid = str(item.get("object_id") or "")
            root = roots.get(page)
            if root is None:
                issues.append({"severity": "blocker", "code": "geometry_slide_missing", "object_id": oid, "page": page})
                continue
            matches = [
                node for node in root.findall(".//p:sp", NS)
                if (
                    node.find("p:nvSpPr/p:cNvPr", NS) is not None
                    and _object_name_matches(node.find("p:nvSpPr/p:cNvPr", NS).get("name"), oid)
                )
            ]
            if len(matches) != 1:
                issues.append({"severity": "blocker", "code": "geometry_target_ambiguous", "object_id": oid, "page": page, "matches": len(matches)})
                continue
            sppr = matches[0].find("p:spPr", NS)
            prst = sppr.find("a:prstGeom", NS) if sppr is not None else None
            cust = sppr.find("a:custGeom", NS) if sppr is not None else None
            if primitive == "ROUNDRECT":
                if prst is None or prst.get("prst") != "roundRect":
                    issues.append({"severity": "blocker", "code": "geometry_roundrect_missing_in_ooxml", "object_id": oid})
                else:
                    gd = prst.find("a:avLst/a:gd", NS)
                    expected = round(float((item.get("parameters") or {}).get("corner_radius_norm", 0.12)) * 100000)
                    if gd is None or gd.get("name") != "adj" or gd.get("fmla") != f"val {expected}":
                        issues.append({"severity": "blocker", "code": "geometry_roundrect_adjustment_mismatch", "object_id": oid})
            elif primitive in {"TRAPEZOID", "FUNNEL"}:
                path = cust.find("a:pathLst/a:path", NS) if cust is not None else None
                actual = _path_points(path) if path is not None else []
                expected = _expected_points(item.get("parameters") or {})
                if path is None or len(actual) < 4:
                    issues.append({"severity": "blocker", "code": "geometry_directional_path_missing", "object_id": oid})
                elif actual[:4] != expected:
                    issues.append({"severity": "blocker", "code": "geometry_directional_path_mismatch", "object_id": oid, "expected": expected, "actual": actual[:4]})
                if path is not None and path.find("a:close", NS) is None:
                    issues.append({"severity": "blocker", "code": "geometry_directional_path_not_closed", "object_id": oid})
            elif primitive == "FREEFORM_BEZIER":
                parameters = item.get("parameters") or {}
                controls = _control_points(parameters)
                expected_count = max(1, (len(controls) - 1) // 3) if controls else 1
                path = cust.find("a:pathLst/a:path", NS) if cust is not None else None
                cubic_nodes = path.findall("a:cubicBezTo", NS) if path is not None else []
                count = len(cubic_nodes)
                if path is None or count != expected_count:
                    issues.append({"severity": "blocker", "code": "geometry_cubic_bezier_missing_in_ooxml", "object_id": oid, "expected": expected_count, "actual": count})
                if controls is None or len(controls) < 4 or (len(controls) - 1) % 3:
                    issues.append({"severity": "blocker", "code": "geometry_cubic_control_points_invalid", "object_id": oid, "detail": "resolution must provide start plus 3n normalized points"})
                if path is not None and path.findall("a:lnTo", NS):
                    issues.append({"severity": "blocker", "code": "geometry_cubic_segmented_line_fallback", "object_id": oid, "detail": "FREEFORM_BEZIER cannot contain line-segment approximations"})
                actual_controls, malformed = _ooxml_path_control_points(path) if path is not None else ([], [])
                if malformed:
                    issues.append({"severity": "blocker", "code": "geometry_cubic_control_point_count_invalid", "object_id": oid, "segments": malformed})
                expected_start = _emu_points(controls[:1]) if controls else []
                actual_start = []
                if path is not None:
                    start = path.find("a:moveTo/a:pt", NS)
                    if start is not None:
                        try:
                            actual_start = [(int(start.get("x", "-1")), int(start.get("y", "-1")))]
                        except (TypeError, ValueError):
                            actual_start = []
                if controls is not None and actual_start != expected_start:
                    issues.append({"severity": "blocker", "code": "geometry_cubic_start_point_mismatch", "object_id": oid, "expected": expected_start, "actual": actual_start})
                if controls is not None and actual_controls != _emu_points(controls[1:]):
                    issues.append({"severity": "blocker", "code": "geometry_cubic_control_points_mismatch", "object_id": oid, "expected": _emu_points(controls[1:]), "actual": actual_controls})
    if has_shape_tree and expected_cubic and actual_cubic < expected_cubic:
        issues.append({"severity": "blocker", "code": "geometry_cubic_bezier_total_missing_in_ooxml", "detail": f"expected at least {expected_cubic}, found {actual_cubic}"})
    return {"schema": SCHEMA, "valid": not issues, "status": "passed" if not issues else "failed", "expected_cubic_bezier_count": expected_cubic, "actual_cubic_bezier_count": actual_cubic, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry_resolution", type=Path)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = audit(load(args.geometry_resolution), args.pptx)
    except Exception as exc:
        result = {"schema": SCHEMA, "valid": False, "status": "failed", "expected_cubic_bezier_count": 0, "actual_cubic_bezier_count": 0, "issues": [{"severity": "blocker", "code": "geometry_authoring_audit_unreadable", "detail": str(exc)}]}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.report:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
