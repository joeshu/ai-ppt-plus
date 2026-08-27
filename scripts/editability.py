#!/usr/bin/env python3
"""Shared L0-L5 editability protocol for slide manifests and release gates."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")
RISK_ORDER = ("L5", "L0", "L4", "L3", "L2", "L1")

TYPE_LEVELS = {
    "editable_text": "L1",
    "native_shape": "L1",
    "editable_vector": "L1",
    "editable_chart": "L1",
    "independent_image": "L2",
    "extracted_icon": "L2",
    "decorative_art": "L2",
    "traceable_static_graphic": "L3",
    "documented_placeholder": "L4",
    "flattened_full_slide": "L0",
    "unresolved": "L5",
}

DECISIONS = {
    "auto-allowed",
    "allowed-with-disclosure",
    "human-confirmation-required",
    "manual-required",
    "blocked",
}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _issue(severity: str, code: str, message: str, index: int, obj: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "object_index": index,
        "object_id": obj.get("object_id"),
    }


def validate_objects(objects: Any) -> List[Dict[str, Any]]:
    """Validate object records and return machine-readable issues."""
    issues: List[Dict[str, Any]] = []
    if not isinstance(objects, list):
        return [{"severity": "blocker", "code": "editability_objects_not_array", "message": "objects must be an array"}]
    seen = set()
    for index, obj in enumerate(objects):
        if not isinstance(obj, dict):
            issues.append({"severity": "blocker", "code": "editability_object_not_object", "object_index": index})
            continue
        object_id = obj.get("object_id")
        if not _nonempty(object_id):
            issues.append(_issue("blocker", "editability_object_id_missing", "object_id is required", index, obj))
        elif object_id in seen:
            issues.append(_issue("blocker", "editability_object_id_duplicate", "object_id must be unique within a slide", index, obj))
        try:
            seen.add(object_id)
        except TypeError:
            issues.append(_issue("blocker", "editability_object_id_unhashable", "object_id must be a scalar identifier", index, obj))
        object_type = obj.get("object_type")
        level = obj.get("editability_level")
        if object_type not in TYPE_LEVELS:
            issues.append(_issue("blocker", "editability_object_type_invalid", "object_type is outside the protocol", index, obj))
        if level not in LEVELS:
            issues.append(_issue("blocker", "editability_level_invalid", "editability_level must be L0-L5", index, obj))
        if object_type in TYPE_LEVELS and level in LEVELS and TYPE_LEVELS[object_type] != level:
            issues.append(_issue("blocker", "editability_type_level_mismatch", f"{object_type} must use {TYPE_LEVELS[object_type]}", index, obj))
        if not isinstance(obj.get("required_for_delivery"), bool):
            issues.append(_issue("blocker", "editability_required_flag_invalid", "required_for_delivery must be boolean", index, obj))
        if level in {"L0", "L5"}:
            issues.append(_issue("blocker", "editability_level_blocked", f"{level} is not deliverable", index, obj))
        if level == "L1" and object_type == "editable_chart" and not (_nonempty(obj.get("data_source")) or _nonempty(obj.get("provenance"))):
            issues.append(_issue("blocker", "editable_chart_data_source_missing", "editable charts need traceable data_source or provenance", index, obj))
        if level == "L2":
            if not (_nonempty(obj.get("provenance")) or _nonempty(obj.get("source_ref")) or _nonempty(obj.get("source_path"))):
                issues.append(_issue("blocker", "independent_image_provenance_missing", "L2 images need provenance or a source reference", index, obj))
            if obj.get("replaceable") is not True:
                issues.append(_issue("blocker", "independent_image_not_replaceable", "L2 images must be explicitly replaceable", index, obj))
            if obj.get("contains_formal_content") is True:
                issues.append(_issue("blocker", "formal_content_rasterized", "formal text or authoritative data cannot be delivered as an L2 image", index, obj))
            if obj.get("human_review_required") is not True:
                issues.append(_issue("blocker", "l2_human_review_not_recorded", "L2 image requires human visual review", index, obj))
        if level == "L3":
            if not (_nonempty(obj.get("provenance")) or _nonempty(obj.get("source_ref")) or _nonempty(obj.get("source_path"))):
                issues.append(_issue("blocker", "traceable_graphic_provenance_missing", "L3 graphics need provenance or a source reference", index, obj))
            if obj.get("reduced_editability_accepted") is not True:
                issues.append(_issue("blocker", "reduced_editability_not_accepted", "L3 requires explicit acceptance of reduced editability", index, obj))
            if obj.get("human_review_required") is not True:
                issues.append(_issue("blocker", "l3_human_review_not_recorded", "L3 graphic requires human confirmation", index, obj))
        if level == "L4":
            if not _nonempty(obj.get("placeholder_reason")):
                issues.append(_issue("blocker", "placeholder_reason_missing", "L4 placeholder needs a reason", index, obj))
            if not _nonempty(obj.get("material_request")):
                issues.append(_issue("blocker", "placeholder_material_request_missing", "L4 placeholder needs a material request", index, obj))
            if obj.get("required_for_delivery") is True:
                issues.append(_issue("blocker", "required_placeholder_blocks_delivery", "a required L4 placeholder blocks delivery", index, obj))
        if level == "L4" and obj.get("human_review_required") is not True:
            issues.append(_issue("blocker", "human_review_required_missing", f"{level} requires human review", index, obj))
    return issues


def _decision(objects: Iterable[Dict[str, Any]]) -> str:
    levels = {obj.get("editability_level") for obj in objects}
    if levels & {"L0", "L5"}:
        return "blocked"
    if any(obj.get("editability_level") == "L4" and obj.get("required_for_delivery") is True for obj in objects):
        return "blocked"
    if "L4" in levels:
        return "manual-required"
    if "L3" in levels:
        return "human-confirmation-required"
    if "L2" in levels:
        return "allowed-with-disclosure"
    return "auto-allowed"


def summarize_objects(objects: Any) -> Dict[str, Any]:
    """Return derived statistics and delivery decision for one page."""
    safe_objects = objects if isinstance(objects, list) else []
    counts = {level: 0 for level in LEVELS}
    for obj in safe_objects:
        if isinstance(obj, dict) and obj.get("editability_level") in counts:
            counts[obj["editability_level"]] += 1
    object_count = len(safe_objects)
    fully_editable = counts["L1"]
    noneditable = counts["L2"] + counts["L3"]
    primary = next((level for level in RISK_ORDER if counts[level]), None)
    return {
        "object_count": object_count,
        "counts_by_level": counts,
        "primary_level": primary,
        "fully_editable_object_count": fully_editable,
        "raster_object_count": noneditable,
        "placeholder_count": counts["L4"],
        "blocked_object_count": counts["L0"] + counts["L5"],
        "fully_editable_ratio": round(fully_editable / object_count, 4) if object_count else 0.0,
        "human_review_required": bool(counts["L2"] or counts["L3"] or counts["L4"] or any(isinstance(obj, dict) and obj.get("human_review_required") is True for obj in safe_objects)),
        "formal_content_rasterized": any(isinstance(obj, dict) and obj.get("contains_formal_content") is True and obj.get("editability_level") != "L1" for obj in safe_objects),
        "delivery_decision": _decision(safe_objects),
    }


def compare_summary(declared: Any, derived: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check optional declared page summary against derived object statistics."""
    if declared is None:
        return []
    if not isinstance(declared, dict):
        return [{"severity": "blocker", "code": "editability_summary_not_object", "message": "editability summary must be an object"}]
    issues: List[Dict[str, Any]] = []
    for field in ("object_count", "primary_level", "fully_editable_object_count", "raster_object_count", "placeholder_count", "blocked_object_count", "delivery_decision", "human_review_required", "formal_content_rasterized"):
        if field in declared and declared.get(field) != derived.get(field):
            issues.append({"severity": "blocker", "code": "editability_summary_mismatch", "field": field, "declared": declared.get(field), "derived": derived.get(field)})
    if "fully_editable_ratio" in declared:
        try:
            ratio = float(declared.get("fully_editable_ratio"))
        except (TypeError, ValueError):
            ratio = None
        if ratio is None or abs(ratio - derived["fully_editable_ratio"]) > 0.0001:
            issues.append({"severity": "blocker", "code": "editability_summary_mismatch", "field": "fully_editable_ratio", "declared": declared.get("fully_editable_ratio"), "derived": derived["fully_editable_ratio"]})
    if "counts_by_level" in declared and declared.get("counts_by_level") != derived["counts_by_level"]:
        issues.append({"severity": "blocker", "code": "editability_summary_mismatch", "field": "counts_by_level", "declared": declared.get("counts_by_level"), "derived": derived["counts_by_level"]})
    return issues
