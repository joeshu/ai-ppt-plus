#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SCHEMA = "ai-ppt-plus/authoring-plan/v1"
ALLOWED_TYPES = {
    "native_text",
    "native_shape",
    "native_table",
    "native_chart",
    "connector",
    "freeform",
    "imagegen_asset",
}
TYPE_CONTRACT = {
    "native_text": "typography_contract",
    "native_shape": "geometry_contract",
    "native_table": "table_contract",
    "native_chart": "chart_contract",
    "connector": "geometry_contract",
    "freeform": "geometry_contract",
    "imagegen_asset": "asset_contract",
}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def issue(code: str, detail: str, *, object_id: str | None = None) -> dict:
    item = {"severity": "blocker", "code": code, "detail": detail}
    if object_id:
        item["object_id"] = object_id
    return item


def validate_bbox(value) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    if not all(isinstance(v, (int, float)) for v in value):
        return False
    x, y, w, h = value
    if w <= 0 or h <= 0:
        return False
    if min(x, y, w, h) < 0 or max(x, y, w, h) > 1:
        return False
    if x + w > 1.000001 or y + h > 1.000001:
        return False
    return True


def validate(plan: dict) -> dict:
    issues: list[dict] = []
    if plan.get("schema") != SCHEMA:
        issues.append(issue("authoring_plan_schema_invalid", f"expected schema {SCHEMA}"))

    source = plan.get("source")
    if not isinstance(source, dict):
        issues.append(issue("authoring_plan_missing_source", "source binding is required"))
    else:
        if not SHA256_RE.match(str(source.get("sha256", ""))):
            issues.append(issue("authoring_plan_source_sha_invalid", "source.sha256 must be a 64-character SHA-256"))
        if not isinstance(source.get("width_px"), int) or source.get("width_px", 0) <= 0:
            issues.append(issue("authoring_plan_source_dimensions_invalid", "source.width_px must be positive"))
        if not isinstance(source.get("height_px"), int) or source.get("height_px", 0) <= 0:
            issues.append(issue("authoring_plan_source_dimensions_invalid", "source.height_px must be positive"))

    canvas = plan.get("canvas")
    if not isinstance(canvas, dict) or canvas.get("units") not in {"normalized", "px", "pt", "in"}:
        issues.append(issue("authoring_plan_canvas_invalid", "canvas width/height/units are required"))
    elif not all(isinstance(canvas.get(k), (int, float)) and canvas.get(k) > 0 for k in ("width", "height")):
        issues.append(issue("authoring_plan_canvas_invalid", "canvas width and height must be positive"))

    objects = plan.get("objects")
    if not isinstance(objects, list) or not objects:
        issues.append(issue("authoring_plan_objects_missing", "objects must be a non-empty list"))
        objects = []

    by_id: dict[str, dict] = {}
    for obj in objects:
        if not isinstance(obj, dict):
            issues.append(issue("authoring_plan_object_invalid", "every object must be a JSON object"))
            continue
        object_id = obj.get("object_id")
        if not isinstance(object_id, str) or not object_id.strip():
            issues.append(issue("authoring_plan_object_id_missing", "object_id is required"))
            continue
        if object_id in by_id:
            issues.append(issue("authoring_plan_object_id_duplicate", "object_id must be unique", object_id=object_id))
            continue
        by_id[object_id] = obj
        if not isinstance(obj.get("page"), int) or obj.get("page", 0) <= 0:
            issues.append(issue("authoring_plan_page_invalid", "page must be a positive 1-based integer", object_id=object_id))
        if not isinstance(obj.get("semantic_role"), str) or not obj.get("semantic_role", "").strip():
            issues.append(issue("authoring_plan_semantic_role_missing", "semantic_role is required", object_id=object_id))
        impl = obj.get("implementation_type")
        if impl not in ALLOWED_TYPES:
            issues.append(issue("authoring_plan_implementation_invalid", f"implementation_type must be one of {sorted(ALLOWED_TYPES)}", object_id=object_id))
        if not validate_bbox(obj.get("bbox")):
            issues.append(issue("authoring_plan_bbox_invalid", "bbox must be normalized [x,y,w,h] within the source canvas", object_id=object_id))
        if not isinstance(obj.get("z_role"), str) or not obj.get("z_role", "").strip():
            issues.append(issue("authoring_plan_z_role_missing", "z_role is required", object_id=object_id))
        contract = TYPE_CONTRACT.get(impl)
        if contract and not isinstance(obj.get(contract), dict):
            issues.append(issue("authoring_plan_type_contract_missing", f"{impl} requires {contract}", object_id=object_id))

    # Reference integrity.
    for object_id, obj in by_id.items():
        parent = obj.get("parent_id")
        if parent is not None and parent not in by_id:
            issues.append(issue("authoring_plan_parent_unknown", f"parent_id {parent!r} does not exist", object_id=object_id))
        for neighbor in obj.get("protected_neighbors", []) or []:
            if neighbor not in by_id:
                issues.append(issue("authoring_plan_protected_neighbor_unknown", f"protected neighbor {neighbor!r} does not exist", object_id=object_id))
            elif neighbor == object_id:
                issues.append(issue("authoring_plan_protected_neighbor_self", "object cannot protect itself", object_id=object_id))

    # Parent cycles.
    for object_id in by_id:
        seen = set()
        current = object_id
        while current in by_id:
            parent = by_id[current].get("parent_id")
            if parent is None:
                break
            if parent in seen or parent == object_id:
                issues.append(issue("authoring_plan_parent_cycle", "parent relationship contains a cycle", object_id=object_id))
                break
            seen.add(current)
            current = parent

    valid = not issues
    return {
        "schema": "ai-ppt-plus/authoring-plan-validation/v1",
        "valid": valid,
        "status": "passed" if valid else "failed",
        "object_count": len(by_id),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the pre-build AuthoringPlan structural contract.")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {
            "schema": "ai-ppt-plus/authoring-plan-validation/v1",
            "valid": False,
            "status": "failed",
            "object_count": 0,
            "issues": [issue("authoring_plan_unreadable", str(exc))],
        }
    else:
        result = validate(plan)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.report:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
