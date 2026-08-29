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


def _slide_map(data: dict, label: str) -> dict[int, dict]:
    raw = data.get("slides")
    if not isinstance(raw, list):
        raw = [data]
    result: dict[int, dict] = {}
    for index, slide in enumerate(raw, 1):
        if not isinstance(slide, dict):
            raise ValueError(f"{label} slide {index} must be an object")
        try:
            slide_no = int(slide.get("slide_no", index))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} slide {index} has an invalid slide_no") from exc
        if slide_no in result:
            raise ValueError(f"{label} contains duplicate slide_no={slide_no}")
        result[slide_no] = slide
    expected = list(range(1, len(result) + 1))
    if sorted(result) != expected:
        raise ValueError(f"{label} slide numbers must be contiguous from 1: {sorted(result)}")
    return result


def _gate_requirements(layout: dict, slides: list[dict], args) -> dict[str, bool]:
    objects = [obj for slide in slides for obj in (slide.get("objects") or []) if isinstance(obj, dict)]
    icon_objects = [obj for obj in objects if obj.get("object_type") in {"extracted_icon", "editable_vector"} or obj.get("role") in {"icon", "logo", "brand_lockup", "brand-logo", "decorative-art", "illustration", "product-visual", "decoration"}]
    visual_objects = [obj for obj in objects if obj.get("object_type") in {"extracted_icon", "editable_vector", "independent_image", "decorative_art", "traceable_static_graphic"} or obj in icon_objects]
    panel_objects = [obj for obj in objects if obj.get("role") in {"semantic-panel", "panel", "frame-panel"} or obj.get("independent") is True]

    def has_gradient(value) -> bool:
        if isinstance(value, dict):
            if isinstance(value.get("gradient"), dict):
                return True
            return any(has_gradient(child) for child in value.values())
        if isinstance(value, list):
            return any(has_gradient(child) for child in value)
        return False

    has_text = any(obj.get("object_type") == "editable_text" for obj in objects)
    # A visual intermediate is an authority for composition, not a fixed
    # reference image. Treating --visual-source as reference-driven enabled
    # typography-calibration/source-image/reference-audit gates for ordinary
    # visual-creation decks and made the manifest overstate their evidence.
    reference_driven = bool(args.reference)
    return {
        "object_manifest": True,
        "semantic_object_audit": True,
        "manifest_registry": True,
        "text_model": has_text,
        "text_style_map": bool(args.requires_text_style_map) or (reference_driven and has_text),
        "icon_assets": bool(icon_objects) or bool(args.requires_icon_assets),
        "imagegen_assets": bool(args.requires_imagegen_assets) or (reference_driven and bool(visual_objects)),
        "panel_assets": bool(panel_objects) or bool(args.requires_panel_assets),
        "panel_approval": bool(panel_objects) or bool(args.requires_panel_approval),
        "gradient_visual": has_gradient(layout) or bool(args.requires_gradient_visual),
        "source_image_validation": reference_driven,
        "reference_audit": reference_driven,
        "content_inventory": reference_driven and has_text,
        "asset_hashes": bool(visual_objects) or reference_driven,
    }


def build(layout: dict, object_manifest: dict, args) -> dict:
    object_by_no = _slide_map(object_manifest, "object manifest")
    layout_by_no = _slide_map(layout, "layout")
    if set(object_by_no) != set(layout_by_no):
        raise ValueError(f"layout/object manifest slide coverage mismatch: layout={sorted(layout_by_no)}, objects={sorted(object_by_no)}")
    slides = []
    for slide_no in sorted(object_by_no):
        object_slide = object_by_no[slide_no]
        objects = object_slide.get("objects")
        if not isinstance(objects, list):
            raise ValueError(f"object manifest slide {slide_no} must contain objects[]")
        summary = summarize_objects(objects)
        counts = summary["counts_by_level"]
        layout_slide = layout_by_no[slide_no]
        placeholders = [obj for obj in objects if isinstance(obj, dict) and obj.get("editability_level") == "L4"]
        blockers = [obj for obj in objects if isinstance(obj, dict) and obj.get("editability_level") in {"L0", "L5"}]
        status = "blocked" if blockers else "placeholder" if placeholders else "complete"
        placeholder_reasons = [obj.get("placeholder_reason") for obj in placeholders if obj.get("placeholder_reason")]
        tradeoffs = [
            {"object_id": obj.get("object_id"), "level": obj.get("editability_level"), "reason": "reduced-editability"}
            for obj in objects if isinstance(obj, dict) and obj.get("editability_level") == "L3"
        ]
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
            "asset_status": status,
            "placeholder_reason": "; ".join(str(item) for item in placeholder_reasons) or None,
            "asset_ids": [
                item.get("object_id") for item in objects
                if isinstance(item, dict) and item.get("editability_level") in {"L2", "L3"}
            ],
            "objects": objects,
            "editability": summary,
            "editable_object_counts": {"L1": counts["L1"]},
            "raster_object_counts": {"L2": counts["L2"], "L3": counts["L3"]},
            "placeholders": [
                {"object_id": obj.get("object_id"), "reason": obj.get("placeholder_reason"), "material_request": obj.get("material_request")}
                for obj in placeholders
            ],
            "substitutions": [],
            "tradeoffs": tradeoffs,
            "render_path": args.render_path,
            "checks": [],
            "issues": [],
            "review_status": args.review_status,
            "requires_icon_assets": any(
                obj.get("object_type") in {"extracted_icon", "editable_vector"}
                or obj.get("role") in {"icon", "logo", "brand_lockup", "brand-logo", "decorative-art", "illustration", "product-visual", "decoration"}
                for obj in objects if isinstance(obj, dict)
            ),
            "requires_imagegen_assets": bool(args.requires_imagegen_assets) or (
                bool(args.reference or args.visual_source) and any(
                    obj.get("object_type") in {"extracted_icon", "editable_vector", "independent_image", "decorative_art", "traceable_static_graphic"}
                    or obj.get("role") in {"icon", "logo", "brand_lockup", "brand-logo", "decorative-art", "illustration", "product-visual", "decoration"}
                    for obj in objects if isinstance(obj, dict)
                )
            ),
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
        "gate_requirements": _gate_requirements(layout, slides, args),
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
    ap.add_argument("--backend", default="python-pptx")
    ap.add_argument("--requires-icon-assets", action="store_true")
    ap.add_argument("--requires-imagegen-assets", action="store_true")
    ap.add_argument("--requires-panel-assets", action="store_true")
    ap.add_argument("--requires-panel-approval", action="store_true")
    ap.add_argument("--requires-text-style-map", action="store_true")
    ap.add_argument("--requires-gradient-visual", action="store_true")
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
