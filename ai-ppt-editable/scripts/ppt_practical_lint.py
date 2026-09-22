#!/usr/bin/env python3
"""Fast OOXML lint for recurring practical PowerPoint reconstruction defects."""
from __future__ import annotations

import argparse
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path, PurePosixPath

from PIL import Image

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main", "p": "http://schemas.openxmlformats.org/presentationml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL_NS = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
EFFECT_TAGS = (b"<a:outerShdw", b"<a:glow", b"<a:softEdge", b"<a:reflection")

def _box(node):
    transform = node.find(".//a:xfrm", NS)
    off = transform.find("a:off", NS) if transform is not None else None
    ext = transform.find("a:ext", NS) if transform is not None else None
    if off is None or ext is None: return None
    return tuple(int(v) for v in (off.get("x", 0), off.get("y", 0), ext.get("cx", 0), ext.get("cy", 0)))

def _overlap_fraction(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    overlap = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))
    return overlap / (aw * ah) if aw > 0 and ah > 0 else 0.0

def _slide_relationships(package, slide_part):
    slide = PurePosixPath(slide_part); rels = slide.parent / "_rels" / f"{slide.name}.rels"
    if str(rels) not in package.namelist(): return {}
    root = ET.fromstring(package.read(str(rels))); result = {}
    for rel in root.findall("pr:Relationship", REL_NS):
        rid, target = rel.get("Id"), rel.get("Target")
        if rid and target: result[rid] = str((slide.parent / target).resolve()) if False else str(PurePosixPath("ppt/slides") / target).replace("ppt/slides/../", "ppt/")
    return result


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
            full_slide_shapes = 0
            ordered = list(root.find(".//p:spTree", NS) or [])
            shape_boxes = []
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
                    full_slide_shapes += 1
                    issues.append({"severity": "warning", "code": "full_slide_shape_background", "part": name})
                if preset is not None and preset.get("prst") == "roundRect" and cx > cy * 4:
                    adjust = props.find(".//a:gd[@name='adj']", NS)
                    if adjust is None:
                        issues.append({"severity": "warning", "code": "rounded_rectangle_default_adjustment", "part": name})
                text = "".join(node.text or "" for node in shape.findall(".//a:t", NS)).strip()
                if text and (cx <= 0 or cy <= 0):
                    issues.append({"severity": "warning", "code": "text_box_not_visible", "part": name, "text": text[:80]})
                if text and (x + cx <= 0 or y + cy <= 0 or x >= slide_cx or y >= slide_cy):
                    issues.append({"severity": "warning", "code": "text_box_outside_slide", "part": name, "text": text[:80]})
                if text and shape.findall(".//a:rPr/a:solidFill//a:alpha[@val='0']", NS):
                    issues.append({"severity": "warning", "code": "text_fully_transparent", "part": name, "text": text[:80]})
                if text in {"→", "⇒", "➜", "➔", "➡"}:
                    issues.append({"severity": "warning", "code": "text_glyph_used_as_arrow", "part": name, "text": text})
                shape_boxes.append((shape, (x, y, cx, cy), preset.get("prst") if preset is not None else None))
            if full_slide_shapes > 1:
                issues.append({"severity": "warning", "code": "duplicate_full_slide_background", "part": name, "count": full_slide_shapes})

            circles = [(box) for _, box, preset in shape_boxes if preset == "ellipse" and box[2] > 0 and box[3] > 0 and abs(box[2] - box[3]) / max(box[2], box[3]) <= 0.05]
            for index, outer in enumerate(circles):
                for inner in circles[index + 1:]:
                    if inner[2] >= outer[2] or _overlap_fraction(inner, outer) < 0.8: continue
                    oc = (outer[0] + outer[2] / 2, outer[1] + outer[3] / 2); ic = (inner[0] + inner[2] / 2, inner[1] + inner[3] / 2)
                    offset = ((oc[0] - ic[0]) ** 2 + (oc[1] - ic[1]) ** 2) ** 0.5 / outer[2]
                    if offset > 0.02: issues.append({"severity": "warning", "code": "circular_overlay_center_offset", "part": name, "normalized_offset": round(offset, 4)})

            for position, node in enumerate(ordered):
                if node.tag != f"{{{NS['p']}}}pic": continue
                picture_box = _box(node)
                if not picture_box: continue
                for later in ordered[position + 1:]:
                    if later.tag != f"{{{NS['p']}}}sp": continue
                    later_box = _box(later); preset = later.find(".//a:prstGeom", NS)
                    if later_box and preset is not None and preset.get("prst") in {"rect", "roundRect"} and later.find(".//a:solidFill", NS) is not None and _overlap_fraction(picture_box, later_box) >= 0.85:
                        issues.append({"severity": "warning", "code": "picture_obscured_by_later_shape", "part": name}); break

            relationships = _slide_relationships(package, name)
            for picture in root.findall(".//p:pic", NS):
                slot = _box(picture); blip = picture.find(".//a:blip", NS); rid = blip.get(f"{{{NS['r']}}}embed") if blip is not None else None; media = relationships.get(rid or "")
                if not slot or not media or media not in names or picture.find(".//a:srcRect", NS) is not None: continue
                try:
                    with Image.open(BytesIO(package.read(media))) as image: source_ratio = image.width / image.height
                    delta = abs((slot[2] / slot[3]) / source_ratio - 1)
                    if delta > 0.08: issues.append({"severity": "warning", "code": "picture_aspect_ratio_distorted", "part": name, "media": media, "ratio_delta": round(delta, 4)})
                except (OSError, ZeroDivisionError): pass

            for connector in root.findall(".//p:cxnSp", NS):
                line = connector.find("p:spPr/a:ln", NS); box = _box(connector)
                if line is None or box is None or (line.find("a:headEnd", NS) is None and line.find("a:tailEnd", NS) is None): continue
                if int(line.get("w", "0") or 0) < 12700 and max(box[2], box[3]) > min(slide_cx, slide_cy) * 0.08:
                    issues.append({"severity": "warning", "code": "thin_connector_used_as_filled_arrow_candidate", "part": name})

        # Transparent assets whose visible subject touches an edge are likely
        # to clip after placement/shadowing. This is package-level and cheap.
        for name in names:
            if not re.fullmatch(r"ppt/media/.*\.(png|PNG)", name):
                continue
            try:
                with Image.open(BytesIO(package.read(name))) as image:
                    if image.mode not in {"RGBA", "LA"} and "transparency" not in image.info:
                        continue
                    alpha = image.convert("RGBA").getchannel("A")
                    bbox = alpha.getbbox()
                    if bbox and (bbox[0] == 0 or bbox[1] == 0 or bbox[2] == image.width or bbox[3] == image.height):
                        issues.append({"severity": "warning", "code": "transparent_subject_touches_edge", "part": name, "bbox": list(bbox), "size": [image.width, image.height]})
            except OSError:
                continue
        slide_xml = b"".join(package.read(name) for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
        if b"<a:ea" not in slide_xml and any(byte >= 0xE4 for byte in slide_xml):
            issues.append({"severity": "warning", "code": "cjk_east_asian_typeface_not_observed"})
    return {"schema": "ai-ppt-plus/ppt-practical-lint/v2", "valid": not any(item["severity"] == "error" for item in issues), "issue_count": len(issues), "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = lint(args.pptx)
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/ppt-practical-lint/v2", "valid": False, "issue_count": 1, "issues": [{"severity": "error", "code": "pptx_lint_failed", "message": str(exc)}]}
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
