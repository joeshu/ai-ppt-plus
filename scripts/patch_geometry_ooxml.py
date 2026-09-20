#!/usr/bin/env python3
"""Apply resolved native geometry to exported PPTX OOXML.

Artifact Tool can author the stable object identity and bounding box, while
PowerPoint's custom geometry is applied here without flattening the object.
The patcher is deliberately ZIP/XML-only and fails closed on ambiguous
object ids, invalid parameters, or incomplete cubic paths.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A, "p": P}
ET.register_namespace("a", A)
ET.register_namespace("p", P)
SCHEMA = "ai-ppt-plus/geometry-ooxml-authoring/v1"
AUTHORABLE = {"ROUNDRECT", "TRAPEZOID", "FUNNEL", "FREEFORM_BEZIER"}


def _q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def _number(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not 0 <= number <= 1:
        raise ValueError(f"{label} must be within 0..1")
    return number


def _point(value: object, label: str) -> tuple[float, float]:
    if isinstance(value, dict):
        x, y = value.get("x"), value.get("y")
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = value[0], value[1]
    else:
        raise ValueError(f"{label} must be [x,y] or {{x,y}}")
    return _number(x, f"{label}.x"), _number(y, f"{label}.y")


def _emu_point(point: tuple[float, float]) -> dict[str, str]:
    return {"x": str(int(round(point[0] * 100000))), "y": str(int(round(point[1] * 100000)))}


def _shape_points(direction: str, taper: float) -> list[tuple[float, float]]:
    narrow = max(0.02, 1.0 - taper)
    side = (1.0 - narrow) / 2.0
    if direction == "down":
        return [(0.0, 0.0), (1.0, 0.0), (0.5 + narrow / 2, 1.0), (0.5 - narrow / 2, 1.0)]
    if direction == "up":
        return [(0.5 - narrow / 2, 0.0), (0.5 + narrow / 2, 0.0), (1.0, 1.0), (0.0, 1.0)]
    if direction == "right":
        return [(0.0, 0.0), (1.0, 0.5 - narrow / 2), (1.0, 0.5 + narrow / 2), (0.0, 1.0)]
    if direction == "left":
        return [(0.0, 0.5 - narrow / 2), (1.0, 0.0), (1.0, 1.0), (0.0, 0.5 + narrow / 2)]
    raise ValueError(f"unsupported direction: {direction}")


def _move_to(parent: ET.Element, point: tuple[float, float]) -> None:
    node = ET.SubElement(parent, _q("a", "moveTo"))
    ET.SubElement(node, _q("a", "pt"), _emu_point(point))


def _line_to(parent: ET.Element, point: tuple[float, float]) -> None:
    node = ET.SubElement(parent, _q("a", "lnTo"))
    ET.SubElement(node, _q("a", "pt"), _emu_point(point))


def _custom_geometry(path: ET.Element) -> ET.Element:
    cust = ET.Element(_q("a", "custGeom"))
    ET.SubElement(cust, _q("a", "avLst"))
    path_list = ET.SubElement(cust, _q("a", "pathLst"))
    path_list.append(path)
    return cust


def _polygon_geometry(points: list[tuple[float, float]]) -> ET.Element:
    path = ET.Element(_q("a", "path"), {"w": "100000", "h": "100000"})
    _move_to(path, points[0])
    for point in points[1:]:
        _line_to(path, point)
    ET.SubElement(path, _q("a", "close"))
    return _custom_geometry(path)


def _cubic_geometry(parameters: dict) -> ET.Element:
    raw = parameters.get("control_points")
    if isinstance(raw, dict):
        raw = [raw.get("start"), raw.get("control1"), raw.get("control2"), raw.get("end")]
    if not isinstance(raw, list) or len(raw) < 4 or (len(raw) - 1) % 3:
        raise ValueError("FREEFORM_BEZIER requires start + 3n cubic control points")
    points = [_point(value, f"control_points[{index}]") for index, value in enumerate(raw)]
    path = ET.Element(_q("a", "path"), {"w": "100000", "h": "100000"})
    _move_to(path, points[0])
    for index in range(1, len(points), 3):
        cubic = ET.SubElement(path, _q("a", "cubicBezTo"))
        for point in points[index:index + 3]:
            ET.SubElement(cubic, _q("a", "pt"), _emu_point(point))
    return _custom_geometry(path)


def _geometry(resolution: dict) -> ET.Element | None:
    primitive = str(resolution.get("primitive") or "").upper()
    parameters = resolution.get("parameters") if isinstance(resolution.get("parameters"), dict) else {}
    if primitive == "ROUNDRECT":
        radius = _number(parameters.get("corner_radius_norm", 0.12), "corner_radius_norm")
        prst = ET.Element(_q("a", "prstGeom"), {"prst": "roundRect"})
        av = ET.SubElement(prst, _q("a", "avLst"))
        ET.SubElement(av, _q("a", "gd"), {"name": "adj", "fmla": f"val {int(round(radius * 100000))}"})
        return prst
    if primitive in {"TRAPEZOID", "FUNNEL"}:
        direction = str(parameters.get("direction") or "down").lower()
        taper = _number(parameters.get("taper_ratio", 0.35), "taper_ratio")
        return _polygon_geometry(_shape_points(direction, taper))
    if primitive == "FREEFORM_BEZIER":
        return _cubic_geometry(parameters)
    if primitive in {"RECT", "ELLIPSE", "FILLED_ARROW", "CONNECTOR", "TABLE", "CHART", "IMAGEGEN_COMPLEX"}:
        return None
    raise ValueError(f"unsupported authoring primitive: {primitive}")


def _slide_name(page: int) -> str:
    if page < 1:
        raise ValueError("page must be >= 1")
    return f"ppt/slides/slide{page}.xml"


def _object_name_matches(name: str | None, object_id: str) -> bool:
    """Match top-level ids and Artifact Tool's group/child stable names."""
    return bool(name) and (name == object_id or name.endswith(f"/{object_id}"))


def _replace_geometry(shape: ET.Element, geometry: ET.Element) -> None:
    sppr = shape.find(_q("p", "spPr"))
    if sppr is None:
        raise ValueError("target shape has no p:spPr")
    for child in list(sppr):
        if child.tag in {_q("a", "prstGeom"), _q("a", "custGeom")}:
            sppr.remove(child)
    if geometry is None:
        return
    xfrm = sppr.find(_q("a", "xfrm"))
    if xfrm is None:
        sppr.insert(0, geometry)
    else:
        index = list(sppr).index(xfrm) + 1
        sppr.insert(index, geometry)


def patch(input_path: Path, output_path: Path, resolution: dict) -> dict:
    if resolution.get("schema") != "ai-ppt-plus/geometry-primitive-resolution/v2":
        raise ValueError("geometry resolution schema is invalid")
    if resolution.get("valid") is not True or resolution.get("repair_required"):
        raise ValueError("geometry resolution is not strict-ready")
    targets = [item for item in resolution.get("resolutions") or [] if str(item.get("primitive") or "").upper() in AUTHORABLE]
    if not targets:
        return {"schema": SCHEMA, "valid": True, "status": "passed", "patched": []}
    by_slide: dict[str, bytes] = {}
    patched: list[str] = []
    bindings: list[dict] = []
    seen: set[tuple[int, str]] = set()
    with zipfile.ZipFile(input_path, "r") as source:
        parts = {info.filename: source.read(info.filename) for info in source.infolist()}
        infos = {info.filename: info for info in source.infolist()}
    for item in targets:
        oid = str(item.get("object_id") or "").strip()
        if not oid:
            raise ValueError("geometry target object_id is required")
        raw_page = item.get("page")
        if raw_page is None:
            raw_page = 1
        if isinstance(raw_page, bool) or not isinstance(raw_page, int) or raw_page < 1:
            raise ValueError(f"geometry target page is invalid for {oid}: {raw_page!r}")
        page = raw_page
        key = (page, oid)
        if key in seen:
            raise ValueError(f"geometry target is duplicated: page {page}, object {oid}")
        seen.add(key)
        name = _slide_name(page)
        if name not in parts:
            raise ValueError(f"slide not found for {oid}: page {page}")
        root = ET.fromstring(parts[name])
        shapes = [node for node in root.findall(".//p:sp", NS) if node.find("p:nvSpPr/p:cNvPr", NS) is not None]
        matches = [
            node for node in shapes
            if _object_name_matches(node.find("p:nvSpPr/p:cNvPr", NS).get("name"), oid)
        ]
        if len(matches) != 1:
            raise ValueError(f"geometry target {oid!r} on page {page} matched {len(matches)} shapes")
        geometry = _geometry(item)
        _replace_geometry(matches[0], geometry)
        parts[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        patched.append(oid)
        bindings.append({"object_id": oid, "page": page, "primitive": str(item.get("primitive") or "").upper()})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{output_path.stem}-", suffix=".pptx", dir=output_path.parent, delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
            for filename, payload in parts.items():
                target.writestr(infos[filename], payload)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"schema": SCHEMA, "valid": True, "status": "passed", "patched": patched, "bindings": bindings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry_resolution", type=Path)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        resolution = json.loads(args.geometry_resolution.read_text(encoding="utf-8"))
        result = patch(args.input, args.output, resolution)
    except Exception as exc:
        result = {"schema": SCHEMA, "valid": False, "status": "failed", "patched": [], "issues": [{"severity": "blocker", "code": "geometry_ooxml_patch_failed", "detail": f"{type(exc).__name__}: {exc}"}]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
