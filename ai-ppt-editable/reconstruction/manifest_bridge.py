#!/usr/bin/env python3
"""Bridge existing ai-ppt-editable manifests/layouts into the reconstruction Graph IR.

The bridge deliberately consumes the existing deterministic authoring truth instead
of inventing a parallel object model.  Layout owns geometry; object-manifest owns
semantic type/editability/provenance; Graph IR becomes the normalized reasoning view.
"""
from __future__ import annotations

from typing import Any

from .graph_ir import PageGraph


OBJECT_TYPE_TO_NODE = {
    "editable_text": "text",
    "native_shape": "shape",
    "editable_table": "table",
    "editable_chart": "chart",
    "editable_vector": "icon",
    "extracted_icon": "icon",
    "native_group": "group",
    "independent_image": "image",
    "traceable_static_graphic": "illustration",
}

_LAYOUT_COLLECTIONS = {
    "texts": "text",
    "shapes": "shape",
    "tables": "table",
    "charts": "chart",
    "icons": "icon",
    "groups": "group",
    "panels": "illustration",
}


def _slides(layout: dict[str, Any]) -> list[dict[str, Any]]:
    slides = layout.get("slides")
    if isinstance(slides, list):
        return [item for item in slides if isinstance(item, dict)]
    return [layout]


def _object_id(item: dict[str, Any], kind: str, index: int) -> str:
    return str(item.get("object_id") or item.get("id") or item.get("name") or item.get("panel_id") or f"{kind}-{index:02d}")


def _bbox(item: dict[str, Any]) -> list[float]:
    if isinstance(item.get("bbox"), (list, tuple)) and len(item["bbox"]) == 4:
        return [float(v) for v in item["bbox"]]
    return [float(item.get("x", 0)), float(item.get("y", 0)), float(item.get("w", 0)), float(item.get("h", 0))]


def _layout_index(layout_slide: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    for collection, kind in _LAYOUT_COLLECTIONS.items():
        for index, item in enumerate(layout_slide.get(collection, []) or [], 1):
            if not isinstance(item, dict):
                continue
            result[_object_id(item, kind, index)] = (kind, item)
    return result


def _semantic(manifest_obj: dict[str, Any], layout_obj: dict[str, Any], node_type: str) -> dict[str, Any]:
    if node_type == "text":
        text_spec = manifest_obj.get("text_spec") if isinstance(manifest_obj.get("text_spec"), dict) else {}
        result = dict(text_spec)
        if "text" not in result and layout_obj.get("text") is not None:
            result["text"] = layout_obj.get("text")
        if "runs" not in result and isinstance(layout_obj.get("runs"), list):
            result["runs"] = layout_obj["runs"]
        return result
    if node_type == "table":
        snapshot = manifest_obj.get("data_snapshot") if isinstance(manifest_obj.get("data_snapshot"), dict) else {}
        return {
            "rows": layout_obj.get("rows", snapshot.get("values", [])),
            "merges": layout_obj.get("merges", manifest_obj.get("merges", [])),
            "native_required": True,
            "data_snapshot": snapshot,
        }
    if node_type == "chart":
        snapshot = manifest_obj.get("data_snapshot") if isinstance(manifest_obj.get("data_snapshot"), dict) else {}
        return {
            "type": layout_obj.get("type", manifest_obj.get("chart_type", "column")),
            "categories": layout_obj.get("categories", snapshot.get("categories", [])),
            "series": layout_obj.get("series", snapshot.get("series", [])),
            "native_required": True,
            "data_snapshot": snapshot,
        }
    return {
        "native_required": bool(manifest_obj.get("native_required")),
        "editability_level": manifest_obj.get("editability_level"),
        "object_type": manifest_obj.get("object_type"),
    }


def _style(layout_obj: dict[str, Any], node_type: str) -> dict[str, Any]:
    excluded = {"object_id", "id", "name", "x", "y", "w", "h", "bbox", "text", "runs", "rows", "merges", "categories", "series", "file", "children", "source_ref"}
    if node_type not in {"text", "shape", "table", "chart"}:
        return {}
    return {key: value for key, value in layout_obj.items() if key not in excluded}


def _source(manifest_obj: dict[str, Any], layout_obj: dict[str, Any]) -> dict[str, Any]:
    source: dict[str, Any] = {}
    file_value = layout_obj.get("file") or manifest_obj.get("source_path") or manifest_obj.get("provenance")
    if file_value:
        source["file"] = str(file_value)
    for key in ("source_sha256", "source_bbox", "asset_policy", "brand_asset_contract"):
        if manifest_obj.get(key) is not None:
            source[key] = manifest_obj[key]
    return source


def build_page_graph(layout: dict[str, Any], object_manifest: dict[str, Any], *, slide_no: int = 1) -> PageGraph:
    """Build one validated PageGraph from existing deterministic evidence."""
    layout_slides = _slides(layout)
    if slide_no < 1 or slide_no > len(layout_slides):
        raise ValueError(f"slide_no {slide_no} out of range")
    manifest_slides = object_manifest.get("slides") or []
    manifest_slide = next((item for item in manifest_slides if isinstance(item, dict) and int(item.get("slide_no", 0)) == slide_no), None)
    if manifest_slide is None:
        raise ValueError(f"object manifest has no slide {slide_no}")

    layout_slide = layout_slides[slide_no - 1]
    layout_by_id = _layout_index(layout_slide)
    nodes: list[dict[str, Any]] = []
    for manifest_obj in manifest_slide.get("objects", []) or []:
        if not isinstance(manifest_obj, dict):
            continue
        object_id = str(manifest_obj.get("object_id") or "").strip()
        if not object_id:
            continue
        layout_match = layout_by_id.get(object_id)
        manifest_type = str(manifest_obj.get("object_type") or "")
        node_type = OBJECT_TYPE_TO_NODE.get(manifest_type)
        if layout_match:
            layout_kind, layout_obj = layout_match
            node_type = node_type or layout_kind
        else:
            layout_obj = {}
        if node_type is None:
            # Unknown release-gate metadata is intentionally not guessed into IR.
            continue
        parent = manifest_obj.get("parent_group")
        node = {
            "id": object_id,
            "type": node_type,
            "bbox": _bbox(layout_obj),
            "role": manifest_obj.get("role"),
            "semantic": _semantic(manifest_obj, layout_obj, node_type),
            "style": _style(layout_obj, node_type),
            "source": _source(manifest_obj, layout_obj),
            "confidence": 1.0,
        }
        if parent:
            node["parent_id"] = str(parent)
        nodes.append(node)

    return PageGraph.from_dict({
        "version": "1.0",
        "page": {
            "slide_width_in": float(layout.get("slide_width_in", 13.333333)),
            "slide_height_in": float(layout.get("slide_height_in", 7.5)),
            "reference_width": float(layout.get("ref_width") or 0),
            "reference_height": float(layout.get("ref_height") or 0),
        },
        "nodes": nodes,
        "metadata": {
            "project_id": object_manifest.get("project_id") or layout.get("project_id"),
            "slide_no": slide_no,
            "source_contract": "layout+slide-object-manifest",
        },
    })
