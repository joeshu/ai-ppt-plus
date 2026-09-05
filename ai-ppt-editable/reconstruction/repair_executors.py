#!/usr/bin/env python3
"""Deterministic repair executors for validated RepairPlan actions.

These executors mutate the authoring deck contract, not PPTX XML directly.  The
existing authoring backend remains the single writer of native PowerPoint objects.
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
    return {str(value) for value in (item.get("object_id"), item.get("id"), item.get("name")) if value is not None and str(value)}


def _locate(deck: dict[str, Any], object_id: str) -> tuple[str, dict[str, Any]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for slide in _slides(deck):
        for collection in ("texts", "shapes", "tables", "charts", "icons", "groups"):
            for item in slide.get(collection, []) or []:
                if isinstance(item, dict) and object_id in _candidate_ids(item):
                    matches.append((collection, item))
    if not matches:
        raise RepairExecutionError(f"object {object_id!r} not found in authoring deck")
    if len(matches) > 1:
        raise RepairExecutionError(f"object {object_id!r} is ambiguous across authoring deck")
    return matches[0]


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
        if "text" not in item:
            item["text"] = "".join(str(run.get("text", "")) for run in runs)


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
        # Cross-type conversion is structural and must be handled by an explicit
        # semantic reconstruction stage, never by an in-place patch.
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


def execute_action(deck: dict[str, Any], action: RepairAction) -> None:
    collection, item = _locate(deck, action.object_id)
    if action.engine == "typography_repair":
        if collection != "texts":
            raise RepairExecutionError("typography repair may only target native text objects")
        _apply_typography(item, action.patch)
        return
    if action.engine == "semantic_repair":
        _apply_semantic(collection, item, action.patch)
        return
    raise RepairExecutionError(f"executor not implemented for {action.engine}")


def execute_plan(deck: dict[str, Any], plan: RepairPlan, *, engines: set[str] | None = None) -> dict[str, Any]:
    """Return a repaired copy plus a deterministic execution report.

    Unsupported engines are left for their dedicated executor and reported as
    skipped rather than being silently approximated.
    """
    repaired = deepcopy(deck)
    allowed = engines or {"typography_repair", "semantic_repair"}
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for action in plan.actions:
        if action.engine not in allowed:
            skipped.append({"finding_id": action.finding_id, "object_id": action.object_id, "engine": action.engine})
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
            "deferred": [dict(item) for item in plan.deferred],
            "valid": not plan.has_blocking_deferred,
        },
    }
