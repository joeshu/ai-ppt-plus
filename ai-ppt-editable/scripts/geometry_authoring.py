#!/usr/bin/env python3
"""Strict bridge from AuthoringPlan geometry resolution to PPTX OOXML."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from patch_geometry_ooxml import patch
from resolve_geometry_primitives import resolve
from validate_geometry_authoring import audit
from enforce_ooxml_font_faces import enforce as enforce_ooxml_font_faces

RESOLUTION_SCHEMA = "ai-ppt-plus/geometry-primitive-resolution/v2"


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
