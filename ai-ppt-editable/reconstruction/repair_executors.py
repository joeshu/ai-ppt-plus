#!/usr/bin/env python3
"""Deterministic repair executors for validated RepairPlan actions.

Repairs mutate the authoring-deck contract, never PPTX XML directly.  The
existing authoring backend remains the single writer of native PowerPoint
objects.  Model-suggested changes only reach this module after RepairRouter has
validated their domain, confidence and patch keys.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .repair_router import RepairAction, RepairPlan


class RepairExecutionError(ValueError):
    pass


def _slides(deck: dict[str, Any]) -> list[dict[str, Any]]:
    slides = deck.get("slides")
    if not isinstance(slides, list):
        raise RepairExecutionError("authoring deck must contain slides[]")
    return slides


def _candidate_ids(item: dict[str, Any]) -> set[str]:
    return {
        str(value)
        for value in (item.get("object_id"), item.get("id"), item.get("name"), item.get("panel_id"))
        if value is not None and str(value)
    }


def _locate(deck: dict[str, Any], object_id: str) -> tuple[str, dict[str, Any]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for slide in _slides(deck):
        for collection in ("texts", "shapes", "tables", "charts", "icons", "groups", "panels"):
            for item in slide.get(collection, []) or []:
                if isinstance(item, dict) and object_id in _candidate_ids(item):
                    matches.append((collection, item))
    if not matches:
        raise RepairExecutionError(f"object {object_id!r} not found in authoring deck")
    if len(matches) > 1:
        raise RepairExecutionError(f"object {object_id!r} is ambiguous across authoring deck")
    return matches[0]


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise RepairExecutionError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RepairExecutionError(f"{label} must be numeric") from exc
    if result != result or result in {float("inf"), float("-inf")}:
        raise RepairExecutionError(f"{label} must be finite")
    return result


def _geometry_bounds(deck: dict[str, Any], item: dict[str, Any]) -> None:
    x = _number(item.get("x", 0.0), "x")
    y = _number(item.get("y", 0.0), "y")
    w = _number(item.get("w", 0.0), "w")
    h = _number(item.get("h", 0.0), "h")
    if w < 0 or h < 0:
        raise RepairExecutionError("geometry width/height must be non-negative")
    units = str(deck.get("units") or "fraction").casefold()
    if units in {"inch", "inches", "in"}:
        sw = _number(deck.get("slide_width_in", 13.333333), "slide_width_in")
        sh = _number(deck.get("slide_height_in", 7.5), "slide_height_in")
        tolerance = 0.02
        if x < -tolerance or y < -tolerance or x + w > sw + tolerance or y + h > sh + tolerance:
            raise RepairExecutionError("geometry patch places object outside slide bounds")
    elif units in {"fraction", "normalized", "relative"}:
        tolerance = 0.002
        if x < -tolerance or y < -tolerance or x + w > 1.0 + tolerance or y + h > 1.0 + tolerance:
            raise RepairExecutionError("geometry patch places normalized object outside slide bounds")


def _apply_geometry(deck: dict[str, Any], item: dict[str, Any], patch: dict[str, Any]) -> None:
    for key in ("x", "y", "w", "h", "rotation"):
        if key in patch:
            item[key] = _number(patch[key], key)
    if "crop" in patch:
        crop = patch["crop"]
        if not isinstance(crop, (dict, list, tuple)):
            raise RepairExecutionError("crop patch must be an object or list")
        item["crop"] = deepcopy(crop)
    if "radius" in patch:
        item["radius"] = _number(patch["radius"], "radius")
    if "padding" in patch:
        padding = patch["padding"]
        if not isinstance(padding, (dict, list, tuple, int, float)) or isinstance(padding, bool):
            raise RepairExecutionError("padding patch must be numeric, list or object")
        item["padding"] = deepcopy(padding)
    if "gap" in patch:
        # A gap is a relation between at least two objects.  Applying it to one
        # object without relation evidence would be ambiguous and cause drift.
        raise RepairExecutionError("gap repair requires relation-aware geometry reconstruction")
    _geometry_bounds(deck, item)


def _apply_typography(item: dict[str, Any], patch: dict[str, Any]) -> None:
    field_map = {
        "font": "font",
        "font_size": "font_size",
        "bold": "bold",
        "italic": "italic",
        "color": "color",
        "line_spacing": "line_spacing",
        "paragraph_spacing": "paragraph_spacing",
        "margin": "margin",
        "autofit": "autofit",
    }
    for source, target in field_map.items():
        if source in patch:
            item[target] = deepcopy(patch[source])
    if "runs" in patch:
        runs = patch["runs"]
        if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
            raise RepairExecutionError("typography runs patch must be a list of objects")
        item["runs"] = deepcopy(runs)
        item["text"] = "".join(str(run.get("text", "")) for run in runs)


def _asset_policy_forbids_crop(item: dict[str, Any]) -> bool:
    policy = str(item.get("asset_policy") or "").casefold()
    contract = item.get("brand_asset_contract")
    return policy == "brand_lockup" or (isinstance(contract, dict) and contract.get("allow_crop") is False)


def _apply_asset(deck: dict[str, Any], item: dict[str, Any], patch: dict[str, Any]) -> None:
    if "scale" in patch:
        scale = _number(patch["scale"], "scale")
        if not 0.25 <= scale <= 4.0:
            raise RepairExecutionError("asset scale must be within [0.25, 4.0]")
        x = _number(item.get("x", 0.0), "x")
        y = _number(item.get("y", 0.0), "y")
        w = _number(item.get("w", 0.0), "w")
        h = _number(item.get("h", 0.0), "h")
        nw, nh = w * scale, h * scale
        item["x"] = x - (nw - w) / 2.0
        item["y"] = y - (nh - h) / 2.0
        item["w"] = nw
        item["h"] = nh
    if "crop" in patch:
        if _asset_policy_forbids_crop(item):
            raise RepairExecutionError("brand-lockup asset contract forbids crop repair")
        crop = patch["crop"]
        if not isinstance(crop, (dict, list, tuple)):
            raise RepairExecutionError("asset crop patch must be an object or list")
        item["crop"] = deepcopy(crop)
    if "rotation" in patch:
        item["rotation"] = _number(patch["rotation"], "rotation")
    if "opacity" in patch:
        opacity = _number(patch["opacity"], "opacity")
        if not 0.0 <= opacity <= 1.0:
            raise RepairExecutionError("asset opacity must be within [0, 1]")
        item["opacity"] = opacity
    if "background_mode" in patch:
        mode = str(patch["background_mode"])
        if mode not in {"transparent", "green", "red", "opaque", "source"}:
            raise RepairExecutionError("unsupported asset background_mode")
        item["background_mode"] = mode
    _geometry_bounds(deck, item)


def _apply_semantic(collection: str, item: dict[str, Any], patch: dict[str, Any]) -> None:
    target_type = patch.get("target_type")
    expected_collection = {
        "text": "texts",
        "shape": "shapes",
        "table": "tables",
        "chart": "charts",
        "icon": "icons",
        "group": "groups",
    }.get(str(target_type)) if target_type is not None else collection
    if target_type is not None and expected_collection != collection:
        raise RepairExecutionError(
            f"semantic repair cannot convert {collection} in-place to {target_type}; rebuild object through native engine"
        )
    if "native_required" in patch:
        item["native_required"] = bool(patch["native_required"])
    if "table_data" in patch:
        if collection != "tables":
            raise RepairExecutionError("table_data patch requires a native table object")
        data = patch["table_data"]
        if not isinstance(data, list) or any(not isinstance(row, list) for row in data):
            raise RepairExecutionError("table_data must be a rectangular row list")
        width = len(data[0]) if data else 0
        if width == 0 or any(len(row) != width for row in data):
            raise RepairExecutionError("table_data rows must be non-empty and rectangular")
        item["rows"] = deepcopy(data)
        item["native_required"] = True
    if "chart_data" in patch:
        if collection != "charts":
            raise RepairExecutionError("chart_data patch requires a native chart object")
        data = patch["chart_data"]
        if not isinstance(data, dict) or not isinstance(data.get("categories"), list) or not isinstance(data.get("series"), list):
            raise RepairExecutionError("chart_data must contain categories[] and series[]")
        item["categories"] = deepcopy(data["categories"])
        item["series"] = deepcopy(data["series"])
        item["native_required"] = True
    if "group_children" in patch:
        if collection != "groups":
            raise RepairExecutionError("group_children patch requires a native group object")
        children = patch["group_children"]
        if not isinstance(children, list) or any(not isinstance(value, str) for value in children):
            raise RepairExecutionError("group_children must be a list of object ids")
        item["children"] = list(children)
    if "connector_targets" in patch:
        raise RepairExecutionError("connector target repair requires connector topology reconstruction")


def execute_action(deck: dict[str, Any], action: RepairAction) -> None:
    collection, item = _locate(deck, action.object_id)
    if action.engine == "geometry_repair":
        _apply_geometry(deck, item, action.patch)
        return
    if action.engine == "typography_repair":
        if collection != "texts":
            raise RepairExecutionError("typography repair may only target native text objects")
        _apply_typography(item, action.patch)
        return
    if action.engine == "asset_repair":
        if collection not in {"icons", "panels"}:
            raise RepairExecutionError("asset repair may only target independently placed asset objects")
        if action.patch.get("regenerate"):
            raise RepairExecutionError("regeneration must be dispatched to the image-generation boundary")
        _apply_asset(deck, item, action.patch)
        return
    if action.engine == "semantic_repair":
        _apply_semantic(collection, item, action.patch)
        return
    raise RepairExecutionError(f"executor not implemented for {action.engine}")


def execute_plan(deck: dict[str, Any], plan: RepairPlan, *, engines: set[str] | None = None) -> dict[str, Any]:
    """Return a repaired copy plus deterministic execution/regeneration reports."""
    repaired = deepcopy(deck)
    allowed = engines or {"geometry_repair", "typography_repair", "asset_repair", "semantic_repair"}
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    regeneration_requests: list[dict[str, Any]] = []
    for action in plan.actions:
        if action.engine not in allowed:
            skipped.append({"finding_id": action.finding_id, "object_id": action.object_id, "engine": action.engine})
            continue
        if action.engine == "asset_repair" and action.requires_regeneration:
            collection, item = _locate(repaired, action.object_id)
            if collection not in {"icons", "panels"}:
                raise RepairExecutionError("asset regeneration may only target independent assets")
            regeneration_requests.append({
                "finding_id": action.finding_id,
                "object_id": action.object_id,
                "source_file": item.get("file"),
                "generation_prompt": action.patch.get("generation_prompt"),
                "background_mode": action.patch.get("background_mode", "transparent"),
                "preserve_geometry": {key: item.get(key) for key in ("x", "y", "w", "h", "rotation") if key in item},
            })
            continue
        execute_action(repaired, action)
        applied.append({
            "finding_id": action.finding_id,
            "object_id": action.object_id,
            "engine": action.engine,
            "patch": deepcopy(action.patch),
        })
    return {
        "deck": repaired,
        "report": {
            "applied": applied,
            "skipped": skipped,
            "regeneration_requests": regeneration_requests,
            "deferred": [dict(item) for item in plan.deferred],
            "valid": not plan.has_blocking_deferred,
            "requires_external_asset_generation": bool(regeneration_requests),
        },
    }
