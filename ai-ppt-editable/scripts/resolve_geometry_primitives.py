#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

SCHEMA = "ai-ppt-plus/geometry-primitive-resolution/v2"
PLAN_SCHEMA = "ai-ppt-plus/authoring-plan/v1"

PRIMITIVES = {
    "RECT", "ROUNDRECT", "ELLIPSE", "TRAPEZOID", "FUNNEL",
    "FILLED_ARROW", "CONNECTOR", "FREEFORM_BEZIER", "TABLE", "CHART",
    "IMAGEGEN_COMPLEX",
}
DIRECTIONS = {"up", "down", "left", "right"}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _num(value, default=None):
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return default


def classify(obj: dict) -> tuple[str, str, list[str], dict]:
    impl = str(obj.get("implementation_type") or "")
    role = str(obj.get("semantic_role") or "").lower()
    g = obj.get("geometry_contract") if isinstance(obj.get("geometry_contract"), dict) else {}
    evidence: list[str] = []
    params: dict = {}

    # Native text is an editable semantic object, not a geometry-bearing
    # primitive.  Keep it in the same resolution ledger so the build binding
    # can account for it without inventing a shape primitive.
    if impl == "native_text":
        return "NATIVE_TEXT", "native text slot has no geometry primitive", ["implementation_type=native_text"], {}

    explicit = str(g.get("primitive_hint") or "").upper()
    if explicit:
        evidence.append("explicit primitive_hint")
        if explicit not in PRIMITIVES:
            return "UNRESOLVED", "unknown primitive_hint", evidence, params
        return explicit, "explicit geometry contract", evidence, resolve_params(explicit, g)

    if impl == "native_table":
        return "TABLE", "native_table implementation", ["implementation_type=native_table"], {}
    if impl == "native_chart":
        return "CHART", "native_chart implementation", ["implementation_type=native_chart"], {}
    if impl == "imagegen_asset":
        return "IMAGEGEN_COMPLEX", "complex visual routed to asset", ["implementation_type=imagegen_asset"], {}

    filled = bool(g.get("filled_body"))
    has_arrowhead = bool(g.get("arrowhead")) or "arrow" in role
    has_shaft = bool(g.get("shaft"))
    stroke_only = bool(g.get("stroke_only"))
    endpoints = g.get("endpoints")
    curvature = str(g.get("curvature") or "").lower()
    requires_cubic = bool(g.get("requires_cubic_bezier")) or curvature in {"cubic", "bezier", "curved", "arc"}
    complex_art = bool(g.get("complex_art")) or bool(g.get("gradient_3d")) or bool(g.get("glow_storytelling"))
    rounded = bool(g.get("rounded_corners")) or "round" in role
    ellipse = bool(g.get("ellipse")) or any(x in role for x in ("circle", "node", "dot"))
    trapezoid = bool(g.get("trapezoid")) or "trapezoid" in role
    funnel = bool(g.get("funnel")) or "funnel" in role

    if complex_art:
        return "IMAGEGEN_COMPLEX", "artistic geometry should not be approximated by native primitive", ["complex_art evidence"], {}
    if requires_cubic:
        return "FREEFORM_BEZIER", "continuous curved path requires cubic Bezier", ["requires_cubic_bezier"], resolve_params("FREEFORM_BEZIER", g)
    if stroke_only and isinstance(endpoints, list) and len(endpoints) == 2:
        return "CONNECTOR", "stroke-only two-endpoint geometry", ["stroke_only", "two endpoints"], resolve_params("CONNECTOR", g)
    if has_arrowhead and filled and has_shaft:
        return "FILLED_ARROW", "filled arrow body with shaft/head", ["filled_body", "shaft", "arrowhead"], resolve_params("FILLED_ARROW", g)
    if funnel:
        return "FUNNEL", "direction-sensitive funnel geometry", ["funnel semantic"], resolve_params("FUNNEL", g)
    if trapezoid:
        return "TRAPEZOID", "direction-sensitive trapezoid geometry", ["trapezoid semantic"], resolve_params("TRAPEZOID", g)
    if ellipse:
        return "ELLIPSE", "ellipse/circle semantic geometry", ["ellipse semantic"], {}
    if rounded:
        return "ROUNDRECT", "rounded rectangular geometry", ["rounded_corners"], resolve_params("ROUNDRECT", g)
    if impl == "connector":
        return "CONNECTOR", "connector implementation", ["implementation_type=connector"], resolve_params("CONNECTOR", g)
    if impl == "freeform":
        return "FREEFORM_BEZIER", "freeform implementation", ["implementation_type=freeform"], resolve_params("FREEFORM_BEZIER", g)
    if impl == "native_shape":
        return "RECT", "default simple native shape", ["implementation_type=native_shape"], {}
    return "UNRESOLVED", "insufficient geometry evidence", evidence, params


def resolve_params(primitive: str, g: dict) -> dict:
    if primitive == "ROUNDRECT":
        radius = _num(g.get("corner_radius_norm"))
        if radius is None:
            radius = _num(g.get("roundrect_adjustment"), 0.12)
        return {"corner_radius_norm": max(0.0, min(radius, 0.5))}
    if primitive in {"TRAPEZOID", "FUNNEL"}:
        direction = str(g.get("direction") or "").lower() or "down"
        # Keep an invalid value visible in the report.  Parameter validation
        # below blocks it; silently turning it into `down` loses the source
        # intent and can produce a convincing but wrong funnel.
        taper = _num(g.get("taper_ratio"), 0.35)
        return {"direction": direction, "taper_ratio": max(0.0, min(taper, 1.0))}
    if primitive == "FILLED_ARROW":
        direction = str(g.get("direction") or "").lower() or "right"
        head = _num(g.get("head_ratio"), 0.28)
        shaft = _num(g.get("shaft_ratio"), 0.42)
        return {
            "direction": direction,
            "head_ratio": max(0.05, min(head, 0.8)),
            "shaft_ratio": max(0.05, min(shaft, 0.9)),
        }
    if primitive == "CONNECTOR":
        return {
            "endpoints": g.get("endpoints"),
            "arrow_start": bool(g.get("arrow_start")),
            "arrow_end": bool(g.get("arrow_end") or g.get("arrowhead")),
        }
    if primitive == "FREEFORM_BEZIER":
        return {
            "requires_cubic_bezier": True,
            "control_points": g.get("control_points") or [],
            "ooxml_requirement": "a:cubicBezTo",
        }
    return {}


def _normalised_points(raw):
    if isinstance(raw, dict):
        raw = [raw.get("start"), raw.get("control1"), raw.get("control2"), raw.get("end")]
    if not isinstance(raw, list):
        return None
    points = []
    for value in raw:
        if isinstance(value, dict):
            x, y = value.get("x"), value.get("y")
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            x, y = value[0], value[1]
        else:
            return None
        x_num, y_num = _num(x), _num(y)
        if x_num is None or y_num is None or not (0 <= x_num <= 1 and 0 <= y_num <= 1):
            return None
        points.append((x_num, y_num))
    return points


def _parameter_issues(primitive: str, geometry: dict, parameters: dict, object_id) -> list[dict]:
    """Return deterministic blockers for parameters that would otherwise be guessed."""
    issues: list[dict] = []

    def add(code: str, detail: str) -> None:
        issues.append({"severity": "blocker", "code": code, "object_id": object_id, "detail": detail})

    if primitive in {"TRAPEZOID", "FUNNEL"}:
        direction = parameters.get("direction")
        if direction not in DIRECTIONS:
            add("geometry_direction_invalid", "direction must be one of up/down/left/right")
        if "direction" in geometry and not isinstance(geometry.get("direction"), str):
            add("geometry_direction_invalid", "direction must be a string")
        if "taper_ratio" in geometry:
            taper = _num(geometry.get("taper_ratio"))
            if taper is None or not 0 <= taper <= 1:
                add("geometry_taper_ratio_invalid", "taper_ratio must be a finite number within 0..1")

    if primitive == "ROUNDRECT":
        key = "corner_radius_norm" if "corner_radius_norm" in geometry else "roundrect_adjustment" if "roundrect_adjustment" in geometry else None
        if key:
            radius = _num(geometry.get(key))
            if radius is None or not 0 <= radius <= 0.5:
                add("geometry_roundrect_adjustment_invalid", "corner radius/adjustment must be a finite number within 0..0.5")

    if primitive == "FILLED_ARROW":
        if parameters.get("direction") not in DIRECTIONS:
            add("geometry_direction_invalid", "filled arrow direction must be one of up/down/left/right")
        for key, lower, upper in (("head_ratio", 0.05, 0.8), ("shaft_ratio", 0.05, 0.9)):
            if key in geometry:
                value = _num(geometry.get(key))
                if value is None or not lower <= value <= upper:
                    add("geometry_arrow_ratio_invalid", f"{key} must be a finite number within {lower}..{upper}")
        if parameters.get("head_ratio", 0) + parameters.get("shaft_ratio", 0) > 1:
            add("geometry_arrow_ratio_sum_invalid", "head_ratio + shaft_ratio must not exceed 1")

    if primitive == "CONNECTOR":
        points = _normalised_points(parameters.get("endpoints"))
        if points is None or len(points) != 2:
            add("geometry_connector_endpoints_invalid", "connector requires exactly two normalized endpoints")

    if primitive == "FREEFORM_BEZIER":
        points = _normalised_points(parameters.get("control_points"))
        if not points:
            add("geometry_cubic_control_points_missing", "FREEFORM_BEZIER requires normalized control points")
        elif len(points) < 4 or (len(points) - 1) % 3:
            add("geometry_cubic_control_points_invalid", "control points must contain start plus 3n cubic points")

    return issues


def expected_impl(primitive: str) -> str | None:
    return {
        "NATIVE_TEXT": "native_text",
        "CONNECTOR": "connector",
        "FREEFORM_BEZIER": "freeform",
        "IMAGEGEN_COMPLEX": "imagegen_asset",
        "TABLE": "native_table",
        "CHART": "native_chart",
        "RECT": "native_shape",
        "ROUNDRECT": "native_shape",
        "ELLIPSE": "native_shape",
        "TRAPEZOID": "native_shape",
        "FUNNEL": "native_shape",
        "FILLED_ARROW": "native_shape",
    }.get(primitive)


def resolve(plan: dict) -> dict:
    issues: list[dict] = []
    resolutions: list[dict] = []
    if plan.get("schema") != PLAN_SCHEMA:
        issues.append({"severity": "blocker", "code": "geometry_plan_schema_invalid", "detail": f"expected {PLAN_SCHEMA}"})
    objects = plan.get("objects")
    if not isinstance(objects, list) or not objects:
        issues.append({"severity": "blocker", "code": "geometry_plan_objects_missing", "detail": "objects must be a non-empty list"})
        objects = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        oid = obj.get("object_id")
        page = obj.get("page")
        impl = obj.get("implementation_type")
        primitive, reason, evidence, params = classify(obj)
        expected = expected_impl(primitive)
        status = "resolved"
        if not isinstance(oid, str) or not oid.strip():
            issues.append({"severity": "blocker", "code": "geometry_object_id_missing", "detail": "geometry object_id is required"})
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            issues.append({"severity": "blocker", "code": "geometry_page_invalid", "object_id": oid, "detail": "page must be a positive 1-based integer"})
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
        parameter_issues = _parameter_issues(primitive, obj.get("geometry_contract") if isinstance(obj.get("geometry_contract"), dict) else {}, params, oid)
        if parameter_issues:
            status = "blocked"
            issues.extend(parameter_issues)
        resolutions.append({
            "object_id": oid,
            "page": page,
            "semantic_role": obj.get("semantic_role"),
            "declared_implementation_type": impl,
            "primitive": primitive,
            "expected_implementation_type": expected,
            "parameters": params,
            "status": status,
            "reason": reason,
            "evidence": evidence,
            "parameter_issues": parameter_issues,
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
