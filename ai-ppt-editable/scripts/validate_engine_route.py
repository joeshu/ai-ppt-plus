#!/usr/bin/env python3
"""Enforce the singular, fail-closed production engine route."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json


EDITABLE_ROUTES = {"reference-reconstruction", "editable-pptx", "native-authoring"}
PRIMARY_BY_ROUTE = {
    "reference-reconstruction": "ai-ppt-editable",
    "editable-pptx": "ai-ppt-editable",
    "native-authoring": "ai-ppt-editable",
    "visual-creation": "ai-ppt-visual-gen",
}
FALLBACK_POLICY_BY_ROUTE = {route: "none" for route in PRIMARY_BY_ROUTE}
EDITABILITY_POLICY_BY_ROUTE = {
    "reference-reconstruction": "native-semantic-objects",
    "editable-pptx": "native-semantic-objects",
    "native-authoring": "native-semantic-objects",
    "visual-creation": "image-slide",
}


def _issue(code: str, **details) -> dict:
    return {"severity": "blocker", "code": code, **details}


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


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

    if events:
        issues.append(_issue("fallback_not_allowed_for_route", route=route, event_count=len(events)))

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
