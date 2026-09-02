#!/usr/bin/env python3
"""Enforce the engine-selection contract before editable PPTX work starts.

The repository has three business skills. GordenImage2PPTX is not a fourth
skill and is never the primary route. It is an explicitly recorded,
region-only visual-asset fallback for the editable route.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from atomic_output import atomic_write_json


EDITABLE_ROUTES = {"reference-reconstruction", "editable-pptx", "native-authoring"}
PRIMARY_BY_ROUTE = {
    "reference-reconstruction": "ai-ppt-editable",
    "editable-pptx": "ai-ppt-editable",
    "native-authoring": "ai-ppt-editable",
    "visual-creation": "ai-ppt-visual-gen",
}
FALLBACK_POLICY_BY_ROUTE = {
    "reference-reconstruction": "scoped-visual-only",
    "editable-pptx": "scoped-visual-only",
    "native-authoring": "none",
    "visual-creation": "none",
}
EDITABILITY_POLICY_BY_ROUTE = {
    "reference-reconstruction": "native-semantic-objects",
    "editable-pptx": "native-semantic-objects",
    "native-authoring": "native-semantic-objects",
    "visual-creation": "image-slide",
}
FALLBACK_ENGINE = "GordenImage2PPTX"
ALLOWED_FALLBACK_ROLES = {
    "icon",
    "decoration",
    "artistic-typography",
    "complex-gradient",
    "illustration",
    "background-texture",
    "decorative-art",
}
FORBIDDEN_FALLBACK_ROLES = {
    "formal-text",
    "semantic-panel",
    "panel-frame",
    "table",
    "chart",
    "card-frame",
    "whole-slide",
    "whole-page",
    "framework",
}
FORBIDDEN_FALLBACK_TYPES = {
    "editable_text",
    "editable_table",
    "editable_chart",
    "native_shape",
    "native_group",
}


def _issue(code: str, **details) -> dict:
    return {"severity": "blocker", "code": code, **details}


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_region(value) -> bool:
    if isinstance(value, dict):
        values = [value.get(key) for key in ("x", "y", "w", "h")]
    elif isinstance(value, (list, tuple)) and len(value) == 4:
        values = list(value)
    else:
        return False
    try:
        numbers = [float(item) for item in values]
    except (TypeError, ValueError):
        return False
    return all(math.isfinite(item) for item in numbers) and numbers[2] > 0 and numbers[3] > 0


def validate_engine_route_data(data: dict, *, strict: bool = True) -> tuple[list[dict], dict]:
    """Return blocking issues and a compact evidence summary."""
    issues: list[dict] = []
    if not isinstance(data, dict):
        return [_issue("route_decision_not_object")], {}

    route = data.get("route")
    expected_primary = PRIMARY_BY_ROUTE.get(route)
    expected_fallback_policy = FALLBACK_POLICY_BY_ROUTE.get(route)
    expected_editability_policy = EDITABILITY_POLICY_BY_ROUTE.get(route)
    if expected_primary is None:
        issues.append(_issue("engine_route_unknown_route", route=route))

    primary = data.get("primary_engine")
    if strict or "primary_engine" in data:
        if not _nonempty(primary):
            issues.append(_issue("primary_engine_missing"))
        elif primary == FALLBACK_ENGINE:
            issues.append(_issue("primary_engine_forbidden", engine=primary))
        elif expected_primary and primary != expected_primary:
            issues.append(_issue("primary_engine_mismatch", expected=expected_primary, observed=primary))

    policy = data.get("fallback_policy")
    if strict or "fallback_policy" in data:
        if policy != expected_fallback_policy:
            issues.append(_issue("fallback_policy_mismatch", expected=expected_fallback_policy, observed=policy))

    editability_policy = data.get("editable_object_policy")
    if strict or "editable_object_policy" in data:
        if editability_policy != expected_editability_policy:
            issues.append(_issue("editable_object_policy_mismatch", expected=expected_editability_policy, observed=editability_policy))

    events = data.get("fallback_events")
    if events is None and not strict:
        events = []
    if not isinstance(events, list):
        issues.append(_issue("fallback_events_invalid"))
        events = []

    fallback_used = data.get("fallback_used")
    if not isinstance(fallback_used, bool):
        if strict:
            issues.append(_issue("fallback_used_missing"))
        fallback_used = bool(events)
    if fallback_used != bool(events):
        issues.append(_issue("fallback_used_event_mismatch", fallback_used=fallback_used, event_count=len(events)))

    if expected_fallback_policy == "none" and events:
        issues.append(_issue("fallback_not_allowed_for_route", route=route))

    for index, event in enumerate(events):
        if not isinstance(event, dict):
            issues.append(_issue("fallback_event_invalid", index=index))
            continue
        engine = event.get("engine")
        if engine != FALLBACK_ENGINE:
            issues.append(_issue("fallback_engine_invalid", index=index, expected=FALLBACK_ENGINE, observed=engine))
        if event.get("scope") != "region":
            issues.append(_issue("fallback_scope_invalid", index=index, observed=event.get("scope")))
        role = event.get("role")
        if role in FORBIDDEN_FALLBACK_ROLES or role not in ALLOWED_FALLBACK_ROLES:
            issues.append(_issue("fallback_role_forbidden", index=index, role=role))
        if event.get("object_type") in FORBIDDEN_FALLBACK_TYPES:
            issues.append(_issue("fallback_object_type_forbidden", index=index, object_type=event.get("object_type")))
        if event.get("contains_formal_content") is True:
            issues.append(_issue("fallback_contains_formal_content", index=index))
        if event.get("whole_page") is True or event.get("full_page") is True or event.get("allow_full_page") is True:
            issues.append(_issue("fallback_full_page_forbidden", index=index))
        if not _valid_region(event.get("region") or event.get("source_bbox")):
            issues.append(_issue("fallback_region_missing", index=index))
        if not _nonempty(event.get("reason")):
            issues.append(_issue("fallback_reason_missing", index=index))
        asset_record = event.get("asset_record")
        if not isinstance(asset_record, dict) or not _nonempty(asset_record.get("manifest")) or not _nonempty(asset_record.get("asset_id")):
            issues.append(_issue("fallback_asset_record_missing", index=index))
        decision = event.get("user_decision")
        if not isinstance(decision, dict) or decision.get("status") != "approved" or not _nonempty(decision.get("by")) or not _nonempty(decision.get("at")):
            issues.append(_issue("fallback_user_decision_missing", index=index))

    evidence = {
        "route": route,
        "primary_engine": primary,
        "fallback_policy": policy,
        "editable_object_policy": editability_policy,
        "fallback_used": bool(fallback_used),
        "fallback_event_count": len(events),
        "fallback_events": events,
    }
    return issues, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route_decision")
    parser.add_argument("--strict", action="store_true", help="require every route-engine field and every fallback proof")
    parser.add_argument("--report")
    args = parser.parse_args()
    path = Path(args.route_decision).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        data = {}
        issues = [_issue("route_decision_unreadable", message=f"{type(exc).__name__}: {exc}")]
        evidence = {}
    else:
        issues, evidence = validate_engine_route_data(data, strict=args.strict)

    result = {
        "schema": "ai-ppt-plus/engine-route-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "route_file": str(path),
        **evidence,
        "issues": issues,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
