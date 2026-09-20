#!/usr/bin/env python3
"""Strict bridge from AuthoringPlan geometry resolution to PPTX OOXML."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from patch_geometry_ooxml import patch
from resolve_geometry_primitives import resolve
from validate_geometry_authoring import audit
from enforce_ooxml_font_faces import enforce as enforce_ooxml_font_faces

RESOLUTION_SCHEMA = "ai-ppt-plus/geometry-primitive-resolution/v2"
BINDING_SCHEMA = "ai-ppt-plus/geometry-artifact-tool-binding/v1"
AUTHORABLE_PRIMITIVES = {
    "RECT", "ROUNDRECT", "ELLIPSE", "TRAPEZOID", "FUNNEL",
    "FILLED_ARROW", "CONNECTOR", "FREEFORM_BEZIER",
}


def prepare(authoring_plan: Path | None = None, geometry_resolution: Path | None = None) -> dict | None:
    if geometry_resolution:
        value = json.loads(Path(geometry_resolution).read_text(encoding="utf-8"))
    elif authoring_plan:
        value = resolve(json.loads(Path(authoring_plan).read_text(encoding="utf-8")))
    else:
        return None
    if value.get("schema") != RESOLUTION_SCHEMA:
        raise ValueError(f"expected {RESOLUTION_SCHEMA}")
    if value.get("valid") is not True:
        raise ValueError("geometry resolution is not valid")
    if value.get("repair_required"):
        raise ValueError("geometry resolution still requires repair")
    return value


def prepare_cli(authoring_plan: str | None = None, geometry_resolution: str | None = None) -> dict | None:
    return prepare(
        Path(authoring_plan).resolve() if authoring_plan else None,
        Path(geometry_resolution).resolve() if geometry_resolution else None,
    )


def write_resolution_report(output: Path, resolution: dict) -> Path:
    """Materialize the exact resolution consumed by the authoring process."""
    path = output.with_name(f"{output.stem}.geometry-resolution.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resolution, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _layout_object_ids(slide: dict) -> set[str]:
    ids: set[str] = set()

    def visit(value) -> None:
        if not isinstance(value, dict):
            return
        object_id = value.get("object_id") or value.get("name")
        if isinstance(object_id, str) and object_id.strip():
            ids.add(object_id)
        for child in value.get("children", []) or []:
            visit(child)

    for spec in slide.get("shapes", []) or []:
        visit(spec)
    for group in slide.get("groups", []) or []:
        visit(group)
    return ids


def validate_artifact_tool_binding(deck: dict, resolution: dict) -> dict:
    """Prove every resolved native geometry target exists in the layout."""
    issues: list[dict] = []
    targets: list[dict] = []
    seen: set[tuple[int, str]] = set()
    slides = deck.get("slides") if isinstance(deck.get("slides"), list) else []
    for item in resolution.get("resolutions", []) or []:
        if not isinstance(item, dict) or str(item.get("primitive") or "").upper() not in AUTHORABLE_PRIMITIVES:
            continue
        oid = str(item.get("object_id") or "").strip()
        page = item.get("page") or 1
        primitive = str(item.get("primitive") or "").upper()
        if not oid:
            issues.append({"severity": "blocker", "code": "geometry_binding_object_id_missing", "detail": "geometry target object_id is required"})
            continue
        if not isinstance(page, int) or isinstance(page, bool) or page < 1 or page > len(slides):
            issues.append({"severity": "blocker", "code": "geometry_binding_page_missing", "object_id": oid, "page": page, "detail": "geometry target page is outside the layout"})
            continue
        key = (page, oid)
        if key in seen:
            issues.append({"severity": "blocker", "code": "geometry_binding_duplicate_target", "object_id": oid, "page": page, "detail": "one layout object must have one geometry resolution"})
            continue
        seen.add(key)
        if oid not in _layout_object_ids(slides[page - 1]):
            issues.append({"severity": "blocker", "code": "geometry_binding_target_missing", "object_id": oid, "page": page, "detail": "resolved geometry target is absent from the Artifact Tool layout"})
        targets.append({
            "object_id": oid,
            "page": page,
            "primitive": primitive,
            "parameters": item.get("parameters") if isinstance(item.get("parameters"), dict) else {},
        })
    valid = not issues
    return {
        "schema": BINDING_SCHEMA,
        "valid": valid,
        "status": "passed" if valid else "failed",
        "resolution_sha256": hashlib.sha256(json.dumps(resolution, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "target_count": len(targets),
        "targets": targets,
        "issues": issues,
    }


def bind(output: Path, resolution: dict, *, patch_report: Path, audit_report: Path) -> dict:
    patch_result = patch(output, output, resolution)
    patch_report.parent.mkdir(parents=True, exist_ok=True)
    patch_report.write_text(json.dumps(patch_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_result = audit(resolution, output)
    audit_report.parent.mkdir(parents=True, exist_ok=True)
    audit_report.write_text(json.dumps(audit_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not audit_result.get("valid"):
        raise ValueError("geometry authoring audit failed")
    return {"patch": patch_result, "audit": audit_result}


def bind_if_present(output: Path, resolution: dict | None) -> dict | None:
    if resolution is None:
        return None
    return bind(
        output,
        resolution,
        patch_report=output.with_name(f"{output.stem}.geometry-ooxml-patch.json"),
        audit_report=output.with_name(f"{output.stem}.geometry-authoring-audit.json"),
    )


def postprocess_authoring_output(output: Path, deck: dict, resolution: dict | None) -> None:
    theme = deck.get("theme") if isinstance(deck.get("theme"), dict) else {}
    family = str(theme.get("font") or deck.get("font_family") or "Microsoft YaHei")
    result = enforce_ooxml_font_faces(output, output, family=family)
    output.with_name(f"{output.stem}.ooxml-font-faces.json").write_text(
        json.dumps({"schema": "ai-ppt-plus/ooxml-font-face-binding/v1", **result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    bind_if_present(output, resolution)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--authoring-plan", type=Path)
    parser.add_argument("--geometry-resolution", type=Path)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    args = parser.parse_args()
    try:
        resolution = prepare(args.authoring_plan, args.geometry_resolution)
        if resolution is None:
            raise ValueError("geometry resolution input is required")
        result = bind(args.pptx, resolution, patch_report=args.patch_report, audit_report=args.audit_report)
        print(json.dumps({"schema": "ai-ppt-plus/geometry-authoring-binding/v1", "valid": True, **result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema": "ai-ppt-plus/geometry-authoring-binding/v1", "valid": False, "status": "blocked", "code": "geometry_authoring_binding_failed", "message": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
