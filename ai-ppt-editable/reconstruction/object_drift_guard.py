#!/usr/bin/env python3
"""Detect unauthorized authoring-object drift across repair iterations."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Any


TRACKED_COLLECTIONS = ("texts", "shapes", "tables", "charts", "icons", "groups", "panels")
GEOMETRY_KEYS = ("x", "y", "w", "h", "rotation", "crop", "radius", "padding")
TEXT_KEYS = ("text", "runs")
STYLE_KEYS = (
    "font", "font_size", "bold", "italic", "color", "line_spacing", "paragraph_spacing",
    "margin", "autofit", "fill", "stroke", "opacity", "background_mode",
)
ASSET_KEYS = ("file", "source_sha256", "asset_policy", "generation_provenance")
SEMANTIC_KEYS = ("native_required", "rows", "categories", "series", "children")


@dataclass(frozen=True)
class ObjectFingerprint:
    object_id: str
    collection: str
    geometry_hash: str
    text_hash: str
    style_hash: str
    asset_hash: str
    semantic_hash: str
    overall_hash: str


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _object_id(item: dict[str, Any]) -> str:
    for key in ("object_id", "id", "name", "panel_id"):
        value = item.get(key)
        if value is not None and str(value):
            return str(value)
    return ""


def fingerprint_object(collection: str, item: dict[str, Any]) -> ObjectFingerprint:
    object_id = _object_id(item)
    if not object_id:
        raise ValueError(f"{collection} object is missing a stable id")
    geometry = {key: item.get(key) for key in GEOMETRY_KEYS if key in item}
    text = {key: item.get(key) for key in TEXT_KEYS if key in item}
    style = {key: item.get(key) for key in STYLE_KEYS if key in item}
    asset = {key: item.get(key) for key in ASSET_KEYS if key in item}
    semantic = {key: item.get(key) for key in SEMANTIC_KEYS if key in item}
    parts = {
        "collection": collection,
        "geometry": geometry,
        "text": text,
        "style": style,
        "asset": asset,
        "semantic": semantic,
    }
    return ObjectFingerprint(
        object_id=object_id,
        collection=collection,
        geometry_hash=_hash(geometry),
        text_hash=_hash(text),
        style_hash=_hash(style),
        asset_hash=_hash(asset),
        semantic_hash=_hash(semantic),
        overall_hash=_hash(parts),
    )


def fingerprint_deck(deck: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for slide_index, slide in enumerate(deck.get("slides", []) or [], start=1):
        if not isinstance(slide, dict):
            continue
        for collection in TRACKED_COLLECTIONS:
            for item in slide.get(collection, []) or []:
                if not isinstance(item, dict):
                    continue
                fp = fingerprint_object(collection, item)
                key = fp.object_id
                if key in output:
                    raise ValueError(f"duplicate object id in drift fingerprint: {key}")
                payload = asdict(fp)
                payload["slide"] = slide_index
                output[key] = payload
    return output


def compare_object_drift(before: dict[str, Any], after: dict[str, Any], *, allowed_object_ids: set[str] | None = None) -> dict[str, Any]:
    allowed = set(allowed_object_ids or set())
    before_fp = fingerprint_deck(before)
    after_fp = fingerprint_deck(after)
    drift = []
    missing = []
    added = []

    for object_id in sorted(before_fp):
        if object_id not in after_fp:
            if object_id not in allowed:
                missing.append(object_id)
            continue
        if object_id in allowed:
            continue
        b = before_fp[object_id]
        a = after_fp[object_id]
        changed_domains = [
            domain for domain in ("geometry", "text", "style", "asset", "semantic")
            if b[f"{domain}_hash"] != a[f"{domain}_hash"]
        ]
        if changed_domains or b["collection"] != a["collection"] or b["slide"] != a["slide"]:
            drift.append({
                "object_id": object_id,
                "changed_domains": changed_domains,
                "collection_before": b["collection"],
                "collection_after": a["collection"],
                "slide_before": b["slide"],
                "slide_after": a["slide"],
            })

    for object_id in sorted(after_fp):
        if object_id not in before_fp and object_id not in allowed:
            added.append(object_id)

    valid = not drift and not missing and not added
    return {
        "schema": "ai-ppt-plus/object-drift-report/v1",
        "valid": valid,
        "allowed_object_ids": sorted(allowed),
        "before_count": len(before_fp),
        "after_count": len(after_fp),
        "unauthorized_drift_count": len(drift),
        "unauthorized_missing_count": len(missing),
        "unauthorized_added_count": len(added),
        "drift": drift,
        "missing": missing,
        "added": added,
    }
