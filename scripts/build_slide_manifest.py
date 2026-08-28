#!/usr/bin/env python3
"""Build the canonical slide manifest from a layout and object manifest.

This adapter keeps geometry in ``layout.json`` and semantic ownership in
``slide-object-manifest.json`` while producing the project-level manifest used
by ``validate_manifest.py`` and ``validate_project.py``. It only derives
metadata; it never infers human approval or changes formal content.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json
from editability import summarize_objects


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def page_type(slide: dict, default: str) -> str:
    if default:
        return default
    if slide.get("panels"):
        return "infographic"
    return "title"


def build(layout: dict, object_manifest: dict, args) -> dict:
    object_slides = object_manifest.get("slides")
    if not isinstance(object_slides, list) or not object_slides:
        raise ValueError("object manifest must contain non-empty slides[]")
    layout_slides = layout.get("slides")
    if not isinstance(layout_slides, list):
        layout_slides = [layout]
    slides = []
    for index, object_slide in enumerate(object_slides):
        slide_no = object_slide.get("slide_no", index + 1)
        objects = object_slide.get("objects")
        if not isinstance(objects, list):
            raise ValueError(f"object manifest slide {slide_no} must contain objects[]")
        summary = summarize_objects(objects)
        counts = summary["counts_by_level"]
        layout_slide = layout_slides[index] if index < len(layout_slides) else {}
        slides.append({
            "slide_id": f"S{int(slide_no):02d}",
            "slide_no": slide_no,
            "page_type": page_type(layout_slide, args.page_type),
            "state": args.state,
            "batch_id": args.batch_id,
            "reference_image": args.reference,
            "formal_content_source": args.formal_content_source,
            "visual_source": args.visual_source or args.reference or "layout.json",
            "object_plan": str(Path(args.object_manifest).resolve()),
            "asset_status": "complete",
            "placeholder_reason": None,
            "asset_ids": [
                item.get("object_id") for item in objects
                if isinstance(item, dict) and item.get("editability_level") in {"L2", "L3"}
            ],
            "objects": objects,
            "editability": summary,
            "editable_object_counts": {"L1": counts["L1"]},
            "raster_object_counts": {"L2": counts["L2"], "L3": counts["L3"]},
            "placeholders": [],
            "substitutions": [],
            "tradeoffs": [],
            "render_path": args.render_path,
            "checks": [],
            "issues": [],
            "review_status": args.review_status,
        })
    return {
        "schema_version": "1.1",
        "kind": "slide",
        "schema": "ai-ppt-plus/slide-manifest/v1",
        "project_id": args.project_id or object_manifest.get("project_id", ""),
        "state": args.state,
        "outline_revision": 1,
        "design_system_revision": 1,
        "backend": args.backend,
        "editability_protocol": "L0-L5/v1",
        "assets": [],
        "slides": slides,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layout")
    ap.add_argument("--object-manifest", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--project-id")
    ap.add_argument("--state", default="reconstruction")
    ap.add_argument("--batch-id", default="B01")
    ap.add_argument("--page-type", default="", help="Use a known page type; otherwise infer infographic when panels exist.")
    ap.add_argument("--reference", default=None)
    ap.add_argument("--formal-content-source", default="layout.json")
    ap.add_argument("--visual-source")
    ap.add_argument("--render-path")
    ap.add_argument("--review-status", default="pending-human-closeout")
    ap.add_argument("--backend", default="host-presentation-runtime")
    args = ap.parse_args()
    try:
        layout = read(Path(args.layout))
        object_manifest = read(Path(args.object_manifest))
        result = build(layout, object_manifest, args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
        return 2
    output = Path(args.output)
    atomic_write_json(output, result)
    print(json.dumps({"valid": True, "slides": len(result["slides"]), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
