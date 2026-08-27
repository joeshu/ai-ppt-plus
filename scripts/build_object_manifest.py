#!/usr/bin/env python3
"""Build a semantic object manifest from layout and asset manifests.

Geometry remains in layout.json; this command only creates the canonical
identity/provenance/editability inventory consumed by the release gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path: str | None):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}


def obj(object_id, role, object_type, level, *, required=True, review=False, **extra):
    base = {
        "object_id": object_id,
        "role": role,
        "object_type": object_type,
        "editability_level": level,
        "required_for_delivery": required,
        "human_review_required": review,
    }
    base.update(extra)
    return base


def build(layout: dict, panel_manifest: dict | None, imagegen: dict | None) -> dict:
    slides = layout.get("slides")
    if not isinstance(slides, list):
        slides = [{k: layout[k] for k in ("background", "frame", "panels", "shapes", "icons", "texts") if k in layout}]
    panels_by_file = {}
    for panel in (panel_manifest or {}).get("panels", []):
        if isinstance(panel, dict) and panel.get("file"):
            key = str(panel["file"])
            panels_by_file[key] = panel
            panels_by_file[Path(key).name] = panel
    output = []
    for slide_no, slide in enumerate(slides, 1):
        objects = []
        bg = slide.get("background")
        if bg:
            objects.append(obj(slide.get("background_object_id", "background"), "background", "independent_image", "L2", review=True, replaceable=True, contains_formal_content=False, source_path=str(bg)))
        frame = slide.get("frame")
        if frame:
            objects.append(obj(slide.get("frame_object_id", "frame"), "frame", "traceable_static_graphic", "L3", review=True, reduced_editability_accepted=True, contains_formal_content=False, provenance=str(frame)))
        for i, panel in enumerate(slide.get("panels", []), 1):
            pid = str(panel.get("object_id") or panel.get("panel_id") or f"panel-{i:02d}")
            layout_file = str(panel.get("file", ""))
            evidence = panels_by_file.get(layout_file) or panels_by_file.get(Path(layout_file).name) or {}
            baked = bool(panel.get("formal_text_baked_in", evidence.get("formal_text_baked_in", False)))
            objects.append(obj(pid, "semantic-panel", "traceable_static_graphic", "L3", review=True, reduced_editability_accepted=True, independent=True, contains_formal_content=baked, provenance=str(evidence.get("source") or panel.get("file")), source_bbox=evidence.get("source_bbox")))
        for i, shape in enumerate(slide.get("shapes", []), 1):
            sid = str(shape.get("object_id") or shape.get("name") or f"shape-{i:02d}")
            objects.append(obj(sid, "native-shape", "native_shape", "L1", review=False, contains_formal_content=False))
        for i, icon in enumerate(slide.get("icons", []), 1):
            iid = str(icon.get("object_id") or icon.get("name") or f"icon-{i:02d}")
            role = str(icon.get("role") or "decorative-art")
            objects.append(obj(iid, role, "extracted_icon", "L2", review=True, replaceable=True, contains_formal_content=False, source_path=str(icon.get("file", "")), provenance=str(icon.get("file", ""))))
        for i, text in enumerate(slide.get("texts", []), 1):
            tid = str(text.get("object_id") or text.get("name") or f"text-{i:02d}")
            objects.append(obj(tid, "formal-text", "editable_text", "L1", review=False, contains_formal_content=False, provenance=str(text.get("source_ref") or "layout.json")))
        output.append({"slide_no": slide_no, "objects": objects})
    return {"schema": "ai-ppt-plus/slide-object-manifest/v1", "project_id": layout.get("project_id", ""), "layout_ref": "layout.json", "slides": output}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layout")
    ap.add_argument("--panel-manifest")
    ap.add_argument("--imagegen-manifest")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    data = build(read(args.layout), read(args.panel_manifest) if args.panel_manifest else None, read(args.imagegen_manifest) if args.imagegen_manifest else None)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": True, "slides": len(data["slides"]), "objects": sum(len(s["objects"]) for s in data["slides"]), "output": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
