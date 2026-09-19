#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "ai-ppt-plus/geometry-primitive-resolution/v1"
PLAN_SCHEMA = "ai-ppt-plus/authoring-plan/v1"

NATIVE_TYPES = {"RECT", "ROUNDRECT", "ELLIPSE", "FILLED_ARROW", "CONNECTOR", "FREEFORM_BEZIER", "TABLE", "CHART"}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def classify(obj: dict) -> tuple[str, str, list[str]]:
    impl = str(obj.get("implementation_type") or "")
    role = str(obj.get("semantic_role") or "").lower()
    g = obj.get("geometry_contract") if isinstance(obj.get("geometry_contract"), dict) else {}
    evidence: list[str] = []

    explicit = str(g.get("primitive_hint") or "").upper()
    if explicit:
        evidence.append("explicit primitive_hint")
        if explicit not in NATIVE_TYPES | {"IMAGEGEN_COMPLEX"}:
            return "UNRESOLVED", "unknown primitive_hint", evidence
        return explicit, "explicit geometry contract", evidence

    if impl == "native_table":
        return "TABLE", "native_table implementation", ["implementation_type=native_table"]
    if impl == "native_chart":
        return "CHART", "native_chart implementation", ["implementation_type=native_chart"]
    if impl == "imagegen_asset":
        return "IMAGEGEN_COMPLEX", "complex visual routed to asset", ["implementation_type=imagegen_asset"]

    filled = bool(g.get("filled_body"))
    has_arrowhead = bool(g.get("arrowhead")) or "arrow" in role
    has_shaft = bool(g.get("shaft"))
    stroke_only = bool(g.get("stroke_only"))
    endpoints = g.get("endpoints")
    curvature = str(g.get("curvature") or "").lower()
    requires_cubic = bool(g.get("requires_cubic_bezier")) or curvature in {"cubic", "bezier", "curved"}
    complex_art = bool(g.get("complex_art")) or bool(g.get("gradient_3d")) or bool(g.get("glow_storytelling"))
    rounded = bool(g.get("rounded_corners")) or "round" in role
    ellipse = bool(g.get("ellipse")) or any(x in role for x in ("circle", "node", "dot"))

    if complex_art:
        return "IMAGEGEN_COMPLEX", "artistic geometry should not be approximated by native primitive", ["complex_art evidence"]
    if requires_cubic:
        return "FREEFORM_BEZIER", "continuous curved path requires cubic Bezier", ["requires_cubic_bezier"]
    if stroke_only and isinstance(endpoints, list) and len(endpoints) == 2:
        return "CONNECTOR", "stroke-only two-endpoint geometry", ["stroke_only", "two endpoints"]
    if has_arrowhead and filled and has_shaft:
        return "FILLED_ARROW", "filled arrow body with shaft/head", ["filled_body", "shaft", "arrowhead"]
    if ellipse:
        return "ELLIPSE", "ellipse/circle semantic geometry", ["ellipse semantic"]
    if rounded:
        return "ROUNDRECT", "rounded rectangular geometry", ["rounded_corners"]
    if impl in {"connector"}:
        return "CONNECTOR", "connector implementation", ["implementation_type=connector"]
    if impl in {"freeform"}:
        return "FREEFORM_BEZIER", "freeform implementation", ["implementation_type=freeform"]
    if impl == "native_shape":
        return "RECT", "default simple native shape", ["implementation_type=native_shape"]
    return "UNRESOLVED", "insufficient geometry evidence", evidence


def expected_impl(primitive: str) -> str | None:
    return {
        "CONNECTOR": "connector",
        "FREEFORM_BEZIER": "freeform",
        "IMAGEGEN_COMPLEX": "imagegen_asset",
        "TABLE": "native_table",
        "CHART": "native_chart",
        "RECT": "native_shape",
        "ROUNDRECT": "native_shape",
        "ELLIPSE": "native_shape",
        "FILLED_ARROW": "native_shape",
    }.get(primitive)


def resolve(plan: dict) -> dict:
    issues: list[dict] = []
    resolutions: list[dict] = []
    if plan.get("schema") != PLAN_SCHEMA:
        issues.append({"severity": "blocker", "code": "geometry_plan_schema_invalid", "detail": f"expected {PLAN_SCHEMA}"})
    for obj in plan.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        oid = obj.get("object_id")
        impl = obj.get("implementation_type")
        primitive, reason, evidence = classify(obj)
        expected = expected_impl(primitive)
        status = "resolved"
        if primitive == "UNRESOLVED":
            status = "blocked"
            issues.append({"severity": "blocker", "code": "geometry_primitive_unresolved", "object_id": oid, "detail": reason})
        elif expected and impl != expected:
            status = "repair-required"
            issues.append({
                "severity": "major",
                "code": "geometry_implementation_mismatch",
                "object_id": oid,
                "declared": impl,
                "expected": expected,
                "primitive": primitive,
                "detail": "repair AuthoringPlan implementation choice before build",
            })
        resolutions.append({
            "object_id": oid,
            "semantic_role": obj.get("semantic_role"),
            "declared_implementation_type": impl,
            "primitive": primitive,
            "expected_implementation_type": expected,
            "status": status,
            "reason": reason,
            "evidence": evidence,
        })
    blockers = [x for x in issues if x.get("severity") == "blocker"]
    return {
        "schema": SCHEMA,
        "valid": not blockers,
        "status": "failed" if blockers else "passed",
        "repair_required": any(x.get("severity") == "major" for x in issues),
        "resolutions": resolutions,
        "issues": issues,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Resolve AuthoringPlan objects to deterministic PowerPoint geometry primitives.")
    p.add_argument("authoring_plan", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        result = resolve(load(args.authoring_plan))
    except Exception as exc:
        result = {"schema": SCHEMA, "valid": False, "status": "failed", "repair_required": False, "resolutions": [], "issues": [{"severity": "blocker", "code": "geometry_resolution_unreadable", "detail": str(exc)}]}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.report:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
