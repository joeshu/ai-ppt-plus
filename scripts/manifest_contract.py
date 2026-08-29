"""Shared normalization rules for the canonical manifest registry.

The domain manifests remain useful authoring artifacts, but the registry needs
one vocabulary for cross-manifest checks.  This module intentionally contains
only deterministic, dependency-free normalization helpers; it never infers
formal copy, visual authority, or human approval.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


MODEL_NAME = "SlideSpec/RegionSpec/ObjectSpec/AssetSpec"
MODEL_VERSION = "2.0"
EDITABILITY_LEVELS = {"L0", "L1", "L2", "L3", "L4", "L5"}
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def first(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def canonical_bbox(value: Any) -> dict[str, float] | None:
    """Convert legacy [x, y, w, h] boxes and dict boxes to one shape."""
    if isinstance(value, (list, tuple)) and len(value) == 4 and all(is_number(part) for part in value):
        return {key: float(part) for key, part in zip(("x", "y", "w", "h"), value)}
    if isinstance(value, dict) and all(is_number(value.get(key)) for key in ("x", "y", "w", "h")):
        return {key: float(value[key]) for key in ("x", "y", "w", "h")}
    return None


def canonical_polygon(value: Any) -> list[list[float]] | None:
    if not isinstance(value, list) or not value:
        return None
    points = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2 or not all(is_number(part) for part in point):
            return None
        points.append([float(point[0]), float(point[1])])
    return points


def _derived_id(prefix: str, item: dict[str, Any], ordinal: int) -> str:
    payload = {key: value for key, value in item.items() if key not in {"details", "notes"}}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:12]}-{ordinal:02d}"


def canonical_id(item: dict[str, Any], prefix: str, ordinal: int, *keys: str) -> tuple[str, str]:
    value = first(item, *keys)
    if value is None:
        return _derived_id(prefix, item, ordinal), "derived"
    return str(value), "explicit"


def canonical_text_spec(item: dict[str, Any], slide_no: int, ordinal: int) -> dict[str, Any]:
    text_id, id_origin = canonical_id(item, "text", ordinal, "text_id", "object_id", "name")
    raw_runs = item.get("runs")
    runs = []
    if isinstance(raw_runs, list):
        for run_index, raw in enumerate(raw_runs, 1):
            if isinstance(raw, dict):
                run = dict(raw)
                run["run_id"] = str(run.get("run_id") or f"{text_id}.r{run_index:02d}")
                run["text"] = str(run.get("text", ""))
            else:
                run = {"run_id": f"{text_id}.r{run_index:02d}", "text": str(raw)}
            runs.append(run)
    content = item.get("content")
    if content is None:
        content = item.get("text")
    if content is None and isinstance(raw_runs, list):
        content = "".join(run["text"] for run in runs)
    if content is None:
        content = ""
    result: dict[str, Any] = {
        "text_id": text_id,
        "slide_no": slide_no,
        "content": str(content),
        "source_ref": first(item, "source_ref", "provenance"),
        "source_bbox": canonical_bbox(item.get("source_bbox")),
        "bbox": canonical_bbox(first(item, "bbox", "box")),
        "coordinate_space": item.get("coordinate_space", item.get("units")),
        "style": dict(item.get("style")) if isinstance(item.get("style"), dict) else None,
        "runs": runs,
        "wrap": dict(item.get("wrap")) if isinstance(item.get("wrap"), dict) else None,
        "literal_redaction": bool(item.get("literal_redaction")),
        "emphasis_expected": bool(item.get("emphasis_expected")),
        "id_origin": id_origin,
    }
    return {key: value for key, value in result.items() if value is not None}


def canonical_region(item: dict[str, Any], slide_no: int, ordinal: int) -> dict[str, Any] | None:
    region_id, id_origin = canonical_id(item, "region", ordinal, "region_id", "panel_id", "id")
    object_ids = item.get("object_ids")
    if not isinstance(object_ids, list):
        object_id = first(item, "object_id", "panel_id", "object_ref")
        object_ids = [str(object_id)] if object_id not in (None, "") else []
    asset_ids = item.get("asset_ids")
    if not isinstance(asset_ids, list):
        asset_id = first(item, "asset_id", "panel_id")
        asset_ids = [str(asset_id)] if asset_id not in (None, "") else []
    raw_bbox = first(item, "bbox", "source_bbox", "box")
    if raw_bbox is None and all(is_number(item.get(key)) for key in ("x", "y", "w", "h")):
        raw_bbox = [item[key] for key in ("x", "y", "w", "h")]
    result = {
        "region_id": region_id,
        "slide_no": slide_no,
        "role": first(item, "role", "region_role") or "region",
        "bbox": canonical_bbox(raw_bbox),
        "polygon": canonical_polygon(item.get("polygon")),
        "object_ids": [str(value) for value in object_ids if value not in (None, "")],
        "asset_ids": [str(value) for value in asset_ids if value not in (None, "")],
        "source_ref": first(item, "source_ref", "provenance", "source"),
        "source_hash": first(item, "source_hash", "source_sha256"),
        "independent": item.get("independent"),
        "id_origin": id_origin,
    }
    return {key: value for key, value in result.items() if value is not None}


def canonical_object(item: dict[str, Any], slide_no: int, ordinal: int, source_manifest: str) -> dict[str, Any]:
    object_id, id_origin = canonical_id(item, "object", ordinal, "object_id", "id", "name")
    embedded_asset = item.get("embedded_asset")
    asset_ids = item.get("asset_ids")
    if not isinstance(asset_ids, list):
        asset_ids = []
        if isinstance(embedded_asset, str) and embedded_asset:
            asset_ids.append(embedded_asset)
        asset_id = first(item, "asset_id", "source_asset_id")
        if asset_id not in (None, ""):
            asset_ids.append(str(asset_id))
    result = {
        "object_id": object_id,
        "slide_no": slide_no,
        "role": first(item, "role", "object_role") or "object",
        "object_type": first(item, "object_type", "type") or "unresolved",
        "editability_level": first(item, "editability_level", "level"),
        "required_for_delivery": item.get("required_for_delivery"),
        "human_review_required": item.get("human_review_required"),
        "bbox": canonical_bbox(first(item, "bbox", "box")),
        "source_bbox": canonical_bbox(item.get("source_bbox")),
        "polygon": canonical_polygon(item.get("polygon")),
        "z_index": first(item, "z_index", "z"),
        "source_hash": first(item, "source_hash", "source_sha256"),
        "source_ref": first(item, "source_ref", "provenance"),
        "expected_kind": item.get("expected_kind"),
        "editability": item.get("editability"),
        "embedded_asset": embedded_asset,
        "asset_ids": [str(value) for value in asset_ids if value not in (None, "")],
        "text_id": first(item, "text_id") or (object_id if first(item, "object_type", "type") == "editable_text" else None),
        "contains_formal_content": item.get("contains_formal_content"),
        "validation_status": item.get("validation_status"),
        "source_manifest": source_manifest,
        "id_origin": id_origin,
        "details": item,
    }
    return {key: value for key, value in result.items() if value is not None}


def asset_role(item: dict[str, Any]) -> str:
    role = first(item, "role", "asset_role")
    if role:
        return str(role)
    layer = str(item.get("layer") or "").lower()
    if layer in {"background", "background_blend"}:
        return "background"
    if layer in {"frame", "frame_raw", "frame_part"}:
        return "frame"
    if "icon" in layer:
        return "icon"
    return "asset"


def canonical_asset(item: dict[str, Any], source_manifest: str, path_base: str, ordinal: int) -> dict[str, Any]:
    asset_id, id_origin = canonical_id(item, "asset", ordinal, "asset_id", "panel_id", "icon_id", "id", "layer")
    result = {
        "asset_id": asset_id,
        "role": asset_role(item),
        "path": first(item, "asset_path", "path", "file", "output_path", "copied_to"),
        "path_base": path_base,
        "source_ref": first(item, "source_ref", "provenance", "source", "generated_source"),
        "source_bbox": canonical_bbox(first(item, "source_bbox", "bbox", "box")),
        "strategy": first(item, "strategy", "extraction_method", "method", "backend"),
        "editability_level": first(item, "editability_level", "level"),
        "required_for_delivery": item.get("required_for_delivery", item.get("required")),
        "embedded": item.get("embedded"),
        "render_visible": item.get("render_visible"),
        "source_hash": first(item, "source_hash", "asset_sha256", "copied_to_sha256", "sha256"),
        "validation_status": item.get("validation_status"),
        "source_manifest": source_manifest,
        "id_origin": id_origin,
        "details": item,
    }
    return {key: value for key, value in result.items() if value is not None}


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_SHA256.fullmatch(value))
